package com.sentinel.v2;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.app.KeyguardManager;
import android.content.pm.ServiceInfo;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * Always-on background service for Sentinel V2.
 *
 * Keeps polling the PC backend for queued phone actions while the app is closed.
 * It shows a persistent notification with a Stop button. The notification is
 * ongoing, so it cannot be swiped away or cleared until Stop is pressed.
 */
public class SentinelService extends Service {

    static final String PREFS = "sentinel_bg";
    static final String KEY_BACKEND = "backend";
    static final String KEY_APIKEY = "apikey";
    static final String KEY_ENABLED = "enabled";

    static final String ACTION_START = "com.sentinel.v2.BG_START";
    static final String ACTION_STOP = "com.sentinel.v2.BG_STOP";
    static final String ACTION_SEND = "com.sentinel.v2.BG_SEND";
    static final String ACTION_CANCEL = "com.sentinel.v2.BG_CANCEL";
    static final String ACTION_REPOST = "com.sentinel.v2.BG_REPOST";
    static final String EXTRA_ID = "id";

    static final String FG_CHANNEL = "sentinel_service";
    static final String ACT_CHANNEL = "sentinel_default";
    static final String OPEN_CHANNEL = "sentinel_open";
    static final int FG_NOTIFICATION_ID = 4242;
    static final long POLL_MS = 3000;
    static final long BACKOFF_MS = 60000;
    static final long CONFIRM_TTL_MS = 5 * 60 * 1000L;

    private volatile boolean running = false;
    private Thread poller;
    private int notificationCounter = 5000;
    private final Map<String, JSONObject> pendingConfirms = new HashMap<>();
    private final Map<String, Long> pendingCreated = new HashMap<>();

    @Override
    public void onCreate() {
        super.onCreate();
        createChannels();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? null : intent.getAction();
        SharedPreferences prefs = prefs();

        if (ACTION_STOP.equals(action)) {
            stopEverything();
            return START_NOT_STICKY;
        }
        if (ACTION_SEND.equals(action)) {
            handleSend(intent.getStringExtra(EXTRA_ID));
            return START_STICKY;
        }
        if (ACTION_CANCEL.equals(action)) {
            handleCancel(intent.getStringExtra(EXTRA_ID));
            return START_STICKY;
        }
        if (ACTION_REPOST.equals(action)) {
            // The user swiped the Stop notification. Put it straight back while the service is on.
            if (prefs.getBoolean(KEY_ENABLED, false)) startForegroundNow();
            return START_STICKY;
        }

        // ACTION_START, or a system restart after the process was killed (intent == null).
        if (action == null && !prefs.getBoolean(KEY_ENABLED, false)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        startForegroundNow();
        startPolling();
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        running = false;
        if (poller != null) poller.interrupt();
        super.onDestroy();
    }

    // ── Foreground notification with Stop ─────────────────────────────

    private void startForegroundNow() {
        Notification n = buildForegroundNotification();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(FG_NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(FG_NOTIFICATION_ID, n);
        }
    }

    private Notification buildForegroundNotification() {
        Intent stop = new Intent(this, SentinelService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(
            this, 1, stop, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);

        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent openPi = PendingIntent.getActivity(
            this, 2, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);

        return new NotificationCompat.Builder(this, FG_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Sentinel is running")
            .setContentText("Listening for commands from your PC. Press Stop to turn off.")
            .setContentIntent(openPi)
            .setDeleteIntent(repostPendingIntent())
            .setOngoing(true)
            .setAutoCancel(false)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(0, "Stop", stopPi)
            .build();
    }

    private PendingIntent repostPendingIntent() {
        Intent repost = new Intent(this, SentinelService.class).setAction(ACTION_REPOST);
        return PendingIntent.getService(
            this, 3, repost, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private void stopEverything() {
        prefs().edit().putBoolean(KEY_ENABLED, false).apply();
        running = false;
        if (poller != null) poller.interrupt();
        stopForeground(true);
        stopSelf();
    }

    // ── Polling loop ──────────────────────────────────────────────────

    private synchronized void startPolling() {
        if (running) return;
        running = true;
        poller = new Thread(this::pollLoop, "sentinel-phone-poll");
        poller.start();
    }

    private void pollLoop() {
        long wait = POLL_MS;
        while (running) {
            try {
                fetchAndRun();
                wait = POLL_MS;
            } catch (AuthFailure e) {
                // Repeated wrong-key calls count as failed logins on the backend, so back off hard.
                wait = BACKOFF_MS;
            } catch (Exception ignored) {
                wait = POLL_MS;
            }
            try {
                Thread.sleep(wait);
            } catch (InterruptedException e) {
                break;
            }
        }
    }

    private static class AuthFailure extends Exception {}

    private void fetchAndRun() throws Exception {
        SharedPreferences p = prefs();
        String base = p.getString(KEY_BACKEND, "");
        String key = p.getString(KEY_APIKEY, "");
        if (base.isEmpty() || key.isEmpty()) return;

        HttpURLConnection c = (HttpURLConnection) new URL(base + "/phone/pending").openConnection();
        try {
            c.setConnectTimeout(4000);
            c.setReadTimeout(6000);
            c.setRequestProperty("X-Api-Key", key);
            int code = c.getResponseCode();
            if (code == 401 || code == 403) throw new AuthFailure();
            if (code != 200) return;

            JSONArray list = new JSONObject(read(c.getInputStream())).optJSONArray("actions");
            if (list == null) return;
            for (int i = 0; i < list.length(); i++) {
                handle(list.getJSONObject(i));
            }
        } finally {
            c.disconnect();
        }
    }

    private static String read(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
        in.close();
        return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }

    private void handle(JSONObject a) {
        String type = a.optString("type");
        String id = a.optString("id", String.valueOf(System.currentTimeMillis()));
        if ("phone_open_app".equals(type)) {
            postOpenApp(a.optString("app"), id);
        } else if ("phone_search".equals(type)) {
            postSearch(a.optString("query"), id);
        } else if ("phone_notify".equals(type)) {
            askToSend(a, id);
        } else if ("phone_text".equals(type)) {
            askToText(a, id);
        }
    }

    // ── Actions ───────────────────────────────────────────────────────
    // Starting an app or a search from the background is blocked on Android 10+,
    // so these post a tappable notification. Tapping it opens the app or search.

    private void postOpenApp(String app, String id) {
        Intent launch = SentinelPhonePlugin.launchIntentFor(this, app);
        if (launch == null) {
            postPlain("Sentinel", "Cannot open " + app + " on this phone.", id);
            return;
        }
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (tryDirectLaunch(launch)) return;
        PendingIntent pi = PendingIntent.getActivity(
            this, requestCode(id + "open"), launch,
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        postLaunch("Open " + app, pi, id, "open");
    }

    private void postSearch(String query, String id) {
        if (query == null || query.trim().isEmpty()) return;
        try {
            String encoded = URLEncoder.encode(query.trim(), StandardCharsets.UTF_8.name());
            Intent intent = new Intent(Intent.ACTION_VIEW,
                Uri.parse("https://www.google.com/search?q=" + encoded));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            if (tryDirectLaunch(intent)) return;
            PendingIntent pi = PendingIntent.getActivity(
                this, requestCode(id + "search"), intent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            postLaunch("Searching: " + query.trim(), pi, id, "search");
        } catch (Exception ignored) {
        }
    }

    /**
     * Opens the app with the accessibility service when the phone is unlocked and that service is on.
     * Returns false when it can't, so the caller falls back to a notification.
     */
    private boolean tryDirectLaunch(Intent intent) {
        KeyguardManager km = (KeyguardManager) getSystemService(Context.KEYGUARD_SERVICE);
        if (km != null && km.isKeyguardLocked()) return false;
        return SentinelAccessibilityService.launch(intent);
    }

    /**
     * Opens the app right away when the phone is locked or asleep (full-screen intent).
     * On an unlocked screen Android shows it as a pop-up instead, so one tap opens it.
     */
    private void postLaunch(String title, PendingIntent launch, String id, String salt) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        Notification n = new NotificationCompat.Builder(this, OPEN_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText("Tap to open it on your phone.")
            .setContentIntent(launch)
            .setFullScreenIntent(launch, true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setAutoCancel(true)
            .build();
        notifySafe(requestCode(id + salt + "launch"), n);
    }

    private void askToSend(JSONObject a, String id) {
        String title = a.optString("title", "Sentinel");
        String body = a.optString("body", "");
        if (title.isEmpty()) return;

        pendingConfirms.put(id, a);
        pendingCreated.put(id, System.currentTimeMillis());
        pruneConfirms();

        PendingIntent sendPi = servicePi(ACTION_SEND, id, "send");
        PendingIntent cancelPi = servicePi(ACTION_CANCEL, id, "cancel");

        Notification n = new NotificationCompat.Builder(this, ACT_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Send this notification?")
            .setContentText(title + (body.isEmpty() ? "" : ": " + body))
            .setStyle(new NotificationCompat.BigTextStyle().bigText(title + (body.isEmpty() ? "" : "\n" + body)))
            .setAutoCancel(false)
            .setOngoing(false)
            .addAction(0, "Send", sendPi)
            .addAction(0, "Cancel", cancelPi)
            .build();
        notifySafe(requestCode(id + "confirm"), n);
    }

    /**
     * Drafts a text from the PC. The contact is looked up on this phone, and nothing is sent
     * until Thomas taps Send on the notification.
     */
    private void askToText(JSONObject a, String id) {
        String wanted = a.optString("title", "").trim();
        String message = a.optString("body", "").trim();
        if (wanted.isEmpty() || message.isEmpty()) return;

        SentinelTextHelper.Contact c = SentinelTextHelper.findContact(this, wanted);
        if (c == null) {
            postPlain("Text not sent", "No contact named " + wanted + " on this phone. Tap Sync contacts and try again.", id);
            return;
        }

        JSONObject draft = new JSONObject();
        try {
            draft.put("title", c.name);
            draft.put("body", message);
            draft.put("sms_number", c.number);
        } catch (JSONException e) {
            return;
        }
        pendingConfirms.put(id, draft);
        pendingCreated.put(id, System.currentTimeMillis());
        pruneConfirms();

        PendingIntent sendPi = servicePi(ACTION_SEND, id, "send");
        PendingIntent cancelPi = servicePi(ACTION_CANCEL, id, "cancel");

        Notification n = new NotificationCompat.Builder(this, ACT_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Send text to " + c.name + "?")
            .setContentText(message)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(message))
            .setAutoCancel(false)
            .setOngoing(false)
            .addAction(0, "Send", sendPi)
            .addAction(0, "Cancel", cancelPi)
            .build();
        notifySafe(requestCode(id + "confirm"), n);
    }

    private void handleSend(String id) {
        if (id == null) return;
        JSONObject a = pendingConfirms.remove(id);
        pendingCreated.remove(id);
        cancelNotification(requestCode(id + "confirm"));
        if (a == null) return;

        if (a.has("sms_number")) {
            boolean sent = SentinelTextHelper.sendSms(this, a.optString("sms_number"), a.optString("body"));
            String name = a.optString("title", "contact");
            postPlain("Sentinel", sent ? "Text sent to " + name + "." : "Text not sent to " + name + ". Check SMS permission.", id + "result");
            return;
        }

        String title = a.optString("title", "Sentinel");
        String body = a.optString("body", "");
        Notification n = new NotificationCompat.Builder(this, ACT_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .build();
        notifySafe(notificationCounter++, n);
    }

    private void handleCancel(String id) {
        if (id == null) return;
        pendingConfirms.remove(id);
        pendingCreated.remove(id);
        cancelNotification(requestCode(id + "confirm"));
    }

    private void pruneConfirms() {
        long now = System.currentTimeMillis();
        for (String key : new java.util.ArrayList<>(pendingCreated.keySet())) {
            if (now - pendingCreated.get(key) > CONFIRM_TTL_MS) {
                pendingConfirms.remove(key);
                pendingCreated.remove(key);
                cancelNotification(requestCode(key + "confirm"));
            }
        }
    }

    private void postPlain(String title, String body, String id) {
        Notification n = new NotificationCompat.Builder(this, ACT_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .build();
        notifySafe(requestCode(id + "plain"), n);
    }

    private void postTappable(String title, String body, PendingIntent tap, String id) {
        Notification n = new NotificationCompat.Builder(this, ACT_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setContentIntent(tap)
            .setAutoCancel(true)
            .build();
        notifySafe(requestCode(id + "tap"), n);
    }

    // ── Helpers ───────────────────────────────────────────────────────

    private PendingIntent servicePi(String action, String id, String salt) {
        Intent i = new Intent(this, SentinelService.class).setAction(action).putExtra(EXTRA_ID, id);
        return PendingIntent.getService(this, requestCode(id + salt), i,
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private void notifySafe(int notificationId, Notification n) {
        NotificationManagerCompat mgr = NotificationManagerCompat.from(this);
        if (!mgr.areNotificationsEnabled()) return;
        try {
            mgr.notify(notificationId, n);
        } catch (SecurityException ignored) {
            // POST_NOTIFICATIONS not granted yet.
        }
    }

    private void cancelNotification(int notificationId) {
        NotificationManagerCompat.from(this).cancel(notificationId);
    }

    private static int requestCode(String s) {
        return s.hashCode() & 0x7fffffff;
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private void createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        NotificationChannel fg = new NotificationChannel(
            FG_CHANNEL, "Background service", NotificationManager.IMPORTANCE_LOW);
        fg.setDescription("Shows while Sentinel listens for PC commands");
        nm.createNotificationChannel(fg);
        NotificationChannel act = new NotificationChannel(
            ACT_CHANNEL, "Sentinel", NotificationManager.IMPORTANCE_DEFAULT);
        nm.createNotificationChannel(act);
        NotificationChannel open = new NotificationChannel(
            OPEN_CHANNEL, "Open on phone", NotificationManager.IMPORTANCE_HIGH);
        open.setDescription("Apps and searches sent from your PC");
        nm.createNotificationChannel(open);
    }
}
