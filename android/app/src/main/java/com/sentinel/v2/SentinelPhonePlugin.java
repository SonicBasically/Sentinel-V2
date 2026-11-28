package com.sentinel.v2;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.app.ActivityManager;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Environment;
import android.os.StatFs;
import android.content.SharedPreferences;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Limited phone actions for Sentinel V2.
 * Only the apps in APPS can be opened. Anything else is refused.
 * Each entry lists candidate package names; the first installed one is used.
 */
@CapacitorPlugin(
    name = "SentinelPhone",
    permissions = {
        @Permission(strings = { Manifest.permission.POST_NOTIFICATIONS }, alias = "notifications"),
        @Permission(strings = { Manifest.permission.READ_CONTACTS }, alias = "contacts"),
        @Permission(strings = { Manifest.permission.SEND_SMS }, alias = "sms")
    }
)
public class SentinelPhonePlugin extends Plugin {

    private static final String CHANNEL_ID = "sentinel_default";
    private static final String CHANNEL_NAME = "Sentinel";
    private static final int MAX_QUERY_LENGTH = 200;
    private static final int MAX_TEXT_LENGTH = 500;

    private static final Map<String, String[]> APPS = new LinkedHashMap<>();
    static {
        APPS.put("spotify", new String[] { "com.spotify.music" });
        APPS.put("youtube music", new String[] { "com.google.android.apps.youtube.music" });
        APPS.put("youtube", new String[] { "com.google.android.youtube" });
        APPS.put("google maps", new String[] { "com.google.android.apps.maps" });
        APPS.put("chrome", new String[] { "com.android.chrome" });
        APPS.put("messages", new String[] {
            "com.samsung.android.messaging",
            "com.google.android.apps.messaging"
        });

        // Real user-facing apps (anything with a launcher icon on the Galaxy S26, 2026-11-02).
        // System internals and Sentinel itself are not listed.
        add("phone", "com.samsung.android.dialer");
        add("contacts", "com.samsung.android.app.contacts");
        add("google contacts", "com.google.android.contacts");
        add("calendar", "com.samsung.android.calendar");
        add("clock", "com.sec.android.app.clockpackage");
        add("camera", "com.sec.android.app.camera");
        add("gallery", "com.sec.android.gallery3d");
        add("photos", "com.google.android.apps.photos");
        add("calculator", "com.sec.android.app.popupcalculator");
        add("samsung notes", "com.samsung.android.app.notes");
        add("reminder", "com.samsung.android.app.reminder");
        add("samsung health", "com.sec.android.app.shealth");
        add("samsung music", "com.sec.android.app.music");
        add("voice recorder", "com.sec.android.app.voicenote");
        add("galaxy store", "com.sec.android.app.samsungapps");
        add("samsung members", "com.samsung.android.voc");
        add("samsung find", "com.samsung.android.app.find");
        add("samsung tips", "com.samsung.android.app.tips");
        add("theme store", "com.samsung.android.themestore");
        add("smart switch", "com.sec.android.easyMover");
        add("secure folder", "com.samsung.knox.securefolder");
        add("my files", "com.sec.android.app.myfiles");
        add("smartthings", "com.samsung.android.oneconnect");
        add("game launcher", "com.samsung.android.game.gamehome");
        add("good lock", "com.samsung.android.goodlock");
        add("keys cafe", "com.samsung.android.keyscafe");
        add("routines", "com.samsung.android.app.routines");
        add("sound assistant", "com.samsung.android.soundassistant");
        add("display assistant", "com.samsung.android.displayassistant");
        add("samsung wallet", "com.samsung.android.spay");
        add("galaxy raw", "com.samsung.android.app.galaxyraw");
        add("sketchbook", "com.samsung.android.app.sketchbook");
        add("dressroom", "com.samsung.android.app.dressroom");
        add("good catch", "com.samsung.android.app.goodcatch");
        add("moments", "com.samsung.android.app.moments");
        add("bixby", "com.samsung.android.bixby.agent");
        add("samsung tv plus", "com.samsung.android.tvplus");
        add("voicemail", "com.samsung.vvm");
        add("google meet", "com.google.android.apps.tachyon");
        add("google docs", "com.google.android.apps.docs.editors.docs");
        add("gmail", "com.google.android.gm");
        add("google tv", "com.google.android.videos");
        add("google fit", "com.google.android.apps.fitness");
        add("google assistant", "com.google.android.apps.googleassistant");
        add("google translate", "com.google.android.apps.translate");
        add("google wallet", "com.google.android.apps.walletnfcrel");
        add("google classroom", "com.google.android.apps.classroom");
        add("google authenticator", "com.google.android.apps.authenticator2");
        add("google home", "com.google.android.apps.chromecast.app");
        add("find my device", "com.google.android.apps.adm");
        add("android auto", "com.google.android.projection.gearhead");
        add("youtube studio", "com.google.android.apps.youtube.creator");
        add("gemini", "com.google.android.apps.bard");
        add("google", "com.google.android.googlequicksearchbox");
        add("play store", "com.android.vending");
        add("brave", "com.brave.browser");
        add("opera gx", "com.opera.gx");
        add("tor browser", "org.torproject.torbrowser");
        add("samsung internet", "com.sec.android.app.sbrowser");
        add("duckduckgo", "com.duckduckgo.mobile.android");
        add("deepl", "com.deepl.mobiletranslator");
        add("duolingo", "com.duolingo");
        add("chatgpt", "com.openai.chatgpt");
        add("sora", "com.openai.sora");
        add("claude", "com.anthropic.claude");
        add("grok", "ai.x.grok");
        add("polycam", "ai.polycam");
        add("x", "com.twitter.android");
        add("discord", "com.discord");
        add("instagram", "com.instagram.android");
        add("facebook", "com.facebook.katana");
        add("messenger", "com.facebook.orca");
        add("facebook pages", "com.facebook.pages.app");
        add("whatsapp", "com.whatsapp");
        add("telegram", "org.telegram.messenger");
        add("snapchat", "com.snapchat.android");
        add("pinterest", "com.pinterest");
        add("reddit", "com.reddit.frontpage");
        add("tiktok", "com.zhiliaoapp.musically");
        add("netflix", "com.netflix.mediaclient");
        add("disney plus", "com.disney.disneyplus");
        add("crunchyroll", "com.crunchyroll.crunchyroid");
        add("prime video", "com.amazon.avod.thirdpartyclient");
        add("twitch", "tv.twitch.android.app");
        add("roku", "com.roku.remote");
        add("amazon", "com.amazon.mShop.android.shopping");
        add("alexa", "com.amazon.dee.app");
        add("temu", "com.einnovation.temu");
        add("etsy", "com.etsy.android");
        add("walmart", "com.walmart.android");
        add("best buy", "com.bestbuy.android");
        add("dollar general", "com.dollargeneral.android");
        add("mcdonalds", "com.mcdonalds.app");
        add("dairy queen", "com.olo.dairyqueen.production");
        add("denny's", "com.dennys.mobile");
        add("cash app", "com.squareup.cash");
        add("paypal", "com.paypal.android.p2pmobile");
        add("outlook", "com.microsoft.office.outlook");
        add("microsoft office", "com.microsoft.office.officehubrow");
        add("onedrive", "com.microsoft.skydrive");
        add("xbox", "com.microsoft.xboxone.smartglass");
        add("tailscale", "com.tailscale.ipn");
        add("nextcloud", "com.nextcloud.client");
        add("davdroid", "at.bitfire.davdroid");
        add("kde connect", "org.kde.kdeconnect_tp");
        add("join", "com.joaomgcd.join");
        add("truecaller", "com.truecaller");
        add("speedtest", "org.zwanoo.android.speedtest");
        add("malwarebytes", "org.malwarebytes.antimalware");
        add("life360", "com.life360.android.safetymapd");
        add("timetree", "works.jubilee.timetree");
        add("bandlab", "com.bandlab.bandlab");
        add("audiostretch", "com.bandlab.audiostretch");
        add("musicolet", "in.krosbits.musicolet");
        add("poweramp", "com.maxmpz.audioplayer");
        add("spotistats", "dev.netlob.spotistats");
        add("zedge", "net.zedge.android");
        add("frameo", "net.frameo.app");
        add("pokemon go", "com.nianticlabs.pokemongo");
        add("roblox", "com.roblox.client");
        add("solar smash", "com.paradyme.solarsmash");
        add("sonic", "com.sega.sonic1px");
        add("sonic 2", "com.sega.sonic2.runner");
        add("cookie clicker", "org.dashnet.cookieclicker");
        add("akinator", "com.digidust.elokence.akinator.freemium");
        add("steam community", "com.valvesoftware.android.steam.community");
        add("stick warriors", "com.stickman.warriors.stickwarriors.dragon.shadow.fight");
        add("gacha club", "air.com.lunime.gachaclub");
        add("tuya smart life", "com.tuya.smartlife");
        add("sengled", "com.sengled.life2");
        add("shark", "com.sharkninja.shark");
        add("hp printer", "com.hp.printercontrol");
        add("arcade1up", "com.arcade1up.companionappandroid");
        add("aws", "com.aws.android");
        add("bidfta", "com.bidfta.mobile");
        add("campus portal", "com.infinitecampus.student.campusportalhybrid");
        add("schoology", "com.schoology.app");
        add("hardin cs", "com.apptegy.hardincs");
        add("myride", "com.tylertech.myridek12");
        add("skyward", "com.skyward.mobileaccess");
        add("fetch rewards", "com.fetchrewards.fetchrewards.hop");
        add("candle app", "com.encore.candleapp");
        add("dental monitoring", "com.h43.dentalmonitoring");
        add("love counter", "com.dudynets.lovecounter");
        add("daybetter", "com.th.daybetter");
        add("flower launcher", "ginlemon.flowerfree");
        add("icon pack studio", "ginlemon.iconpackstudio");
        add("kustom", "org.kustom.widget");
        add("brevent", "me.piebridge.brevent");
        add("shizuku", "moe.shizuku.privileged.api");
        add("systemui tuner", "com.zacharee1.systemuituner");
        add("auto clicker", "com.truedevelopersstudio.automatictap.autoclicker");
        add("accubattery", "com.digibites.accubattery");
        add("file explorer", "com.cxinventor.file.explorer");
        add("video to mp3", "mp3videoconverter.videotomp3.videotomp3converter");
        add("video to audio", "com.mp3converter.videoconverter.videotomp3.videotoaudio");
        add("zfile", "com.htetznaing.zfile");
        add("zfont", "com.htetznaing.zfont2");
        add("spacedesk", "ph.spacedesk.beta");
        add("sstv encoder", "om.sstvencoder");
        add("robot 36", "xdsopl.robot36");
        add("funny print", "com.lailaixiong.funnyprint");
        add("simeji keyboard", "com.simejikeyboard");
        add("measure", "com.camtoplan.measure");
        add("bmi calculator", "com.codium.bmicalculator");
        add("crumbl", "crumbl.cookies");
        add("widgetable", "com.widgetable.theme.android");
        add("led rgb", "wl.smartled.duoco.rgb");
        add("smart led", "wl.smartled.rgb");
        add("band hero", "com.crrepa.band.hero");
        add("olywear", "com.lianhezhuli.olywear");
        add("webtoapp", "com.webtoapp");
        add("i751", "com.w2a.i751");
        add("xd0a", "com.w2a.xd0a");
        add("beauty", "com.xiaozhen.beauty.hnd");
        add("zwart icons", "com.blackiconpack.zwart");
        add("akbon", "com.akbon.ios");
        add("tone reply", "com.aistudio.tonereply.wxkqpz");
        add("armmc", "com.armmc.app");
    }

    /** Registers one allowlisted app: a friendly name and the package(s) to try, in order. */
    private static void add(String name, String... packages) {
        APPS.put(name, packages);
    }

    private int notificationCounter = 1;

    @PluginMethod
    public void openApp(PluginCall call) {
        String app = normalise(call.getString("app"));
        if (app == null) {
            call.reject("missing_app");
            return;
        }

        // Settings is opened through an intent, not a package.
        if (app.equals("settings")) {
            Intent intent = new Intent(Settings.ACTION_SETTINGS);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(intent);
            call.resolve(result(app, "opened"));
            return;
        }

        String[] packages = APPS.get(app);
        if (packages == null) {
            call.reject("app_not_allowed");
            return;
        }

        PackageManager pm = getContext().getPackageManager();
        for (String pkg : packages) {
            Intent launch = pm.getLaunchIntentForPackage(pkg);
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                getContext().startActivity(launch);
                call.resolve(result(app, "opened"));
                return;
            }
        }
        call.reject("app_not_installed");
    }

    @PluginMethod
    public void search(PluginCall call) {
        String query = call.getString("query");
        if (query == null || query.trim().isEmpty()) {
            call.reject("missing_query");
            return;
        }
        query = query.trim();
        if (query.length() > MAX_QUERY_LENGTH) {
            query = query.substring(0, MAX_QUERY_LENGTH);
        }

        try {
            String encoded = URLEncoder.encode(query, StandardCharsets.UTF_8.name());
            Intent intent = new Intent(Intent.ACTION_VIEW,
                Uri.parse("https://www.google.com/search?q=" + encoded));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(intent);
            call.resolve(result(query, "searched"));
        } catch (Exception e) {
            call.reject("search_failed");
        }
    }

    @PluginMethod
    public void sendNotification(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && getPermissionState("notifications") != PermissionState.GRANTED) {
            requestPermissionForAlias("notifications", call, "notifyPermissionCallback");
            return;
        }
        postNotification(call);
    }

    @PermissionCallback
    private void notifyPermissionCallback(PluginCall call) {
        if (getPermissionState("notifications") == PermissionState.GRANTED) {
            postNotification(call);
        } else {
            call.reject("notifications_denied");
        }
    }

    private void postNotification(PluginCall call) {
        String title = clip(call.getString("title"), MAX_TEXT_LENGTH);
        String body = clip(call.getString("body"), MAX_TEXT_LENGTH);
        if (title == null || title.isEmpty()) {
            call.reject("missing_title");
            return;
        }

        if (!NotificationManagerCompat.from(getContext()).areNotificationsEnabled()) {
            call.reject("notifications_disabled");
            return;
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager manager =
                (NotificationManager) getContext().getSystemService(Context.NOTIFICATION_SERVICE);
            NotificationChannel channel =
                new NotificationChannel(CHANNEL_ID, CHANNEL_NAME, NotificationManager.IMPORTANCE_DEFAULT);
            manager.createNotificationChannel(channel);
        }

        NotificationCompat.Builder builder = new NotificationCompat.Builder(getContext(), CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body == null ? "" : body)
            .setAutoCancel(true);

        int id = notificationCounter++;
        NotificationManagerCompat.from(getContext()).notify(id, builder.build());
        call.resolve(result(title, "sent"));
    }

    /** Launch intent for an allowlisted app, or null if it is not allowed or not installed. */
    static Intent launchIntentFor(Context ctx, String app) {
        String key = app == null ? null : app.trim().toLowerCase();
        if (key == null) return null;
        String[] packages = APPS.get(key);
        if (packages == null) return null;
        PackageManager pm = ctx.getPackageManager();
        for (String pkg : packages) {
            Intent launch = pm.getLaunchIntentForPackage(pkg);
            if (launch != null) return launch;
        }
        return null;
    }

    // ── Always-on background service ──────────────────────────────────

    /** Stores the PC backend address and API key for the background service. */
    @PluginMethod
    public void setConnection(PluginCall call) {
        String backend = call.getString("backend");
        String apiKey = call.getString("apiKey");
        if (backend == null || backend.trim().isEmpty() || apiKey == null || apiKey.trim().isEmpty()) {
            call.reject("missing_connection");
            return;
        }
        // Stored in app-private preferences only. Nothing is sent anywhere except the PC backend.
        getContext().getSharedPreferences(SentinelService.PREFS, Context.MODE_PRIVATE).edit()
            .putString(SentinelService.KEY_BACKEND, backend.trim().replaceAll("/+$", ""))
            .putString(SentinelService.KEY_APIKEY, apiKey.trim())
            .apply();
        call.resolve(result("connection", "saved"));
    }

    /** Starts the foreground service (polls the PC while the app is closed). */
    @PluginMethod
    public void startBackground(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && getPermissionState("notifications") != PermissionState.GRANTED) {
            // Without this permission the service's Stop notification is hidden.
            requestPermissionForAlias("notifications", call, "bgPermissionCallback");
            return;
        }
        startBackgroundNow(call);
    }

    @PermissionCallback
    private void bgPermissionCallback(PluginCall call) {
        startBackgroundNow(call);
    }

    private void startBackgroundNow(PluginCall call) {
        SharedPreferences p = getContext().getSharedPreferences(SentinelService.PREFS, Context.MODE_PRIVATE);
        if (p.getString(SentinelService.KEY_BACKEND, "").isEmpty()
                || p.getString(SentinelService.KEY_APIKEY, "").isEmpty()) {
            call.reject("missing_connection");
            return;
        }
        p.edit().putBoolean(SentinelService.KEY_ENABLED, true).apply();
        Intent i = new Intent(getContext(), SentinelService.class).setAction(SentinelService.ACTION_START);
        ContextCompat.startForegroundService(getContext(), i);
        call.resolve(result("background", "started"));
    }

    /** Stops the service from the page. The notification's Stop button does the same thing. */
    @PluginMethod
    public void stopBackground(PluginCall call) {
        Intent i = new Intent(getContext(), SentinelService.class).setAction(SentinelService.ACTION_STOP);
        getContext().startService(i);
        call.resolve(result("background", "stopped"));
    }

    /** Copies the phone's contacts (names and numbers) to the PC. Runs only when Thomas taps Sync contacts. */
    @PluginMethod
    public void syncContacts(PluginCall call) {
        if (getPermissionState("contacts") != PermissionState.GRANTED) {
            requestPermissionForAlias("contacts", call, "contactsPermissionCallback");
            return;
        }
        runContactSync(call);
    }

    @PermissionCallback
    private void contactsPermissionCallback(PluginCall call) {
        if (getPermissionState("contacts") == PermissionState.GRANTED) {
            runContactSync(call);
        } else {
            call.reject("contacts_denied");
        }
    }

    private void runContactSync(PluginCall call) {
        SharedPreferences p = getContext().getSharedPreferences(SentinelService.PREFS, Context.MODE_PRIVATE);
        String backend = p.getString(SentinelService.KEY_BACKEND, "");
        String apiKey = p.getString(SentinelService.KEY_APIKEY, "");
        if (backend.isEmpty() || apiKey.isEmpty()) {
            call.reject("missing_connection");
            return;
        }
        new Thread(() -> {
            try {
                int count = SentinelTextHelper.syncToPc(getContext(), backend, apiKey);
                JSObject out = new JSObject();
                out.put("status", "synced");
                out.put("count", count);
                out.put("synced", System.currentTimeMillis());
                call.resolve(out);
            } catch (Exception e) {
                call.reject("sync_failed");
            }
        }, "sentinel-contacts-sync").start();
    }

    // Battery, memory, storage and uptime for the Devices panel on the PC. The page sends these
    // as a heartbeat to the PC backend while the app is open. Android does not expose per-app CPU load.
    @PluginMethod
    public void getDeviceStats(PluginCall call) {
        try {
            JSObject out = new JSObject();

            ActivityManager am = (ActivityManager) getContext().getSystemService(Context.ACTIVITY_SERVICE);
            ActivityManager.MemoryInfo mi = new ActivityManager.MemoryInfo();
            am.getMemoryInfo(mi);
            double memTotalGb = mi.totalMem / 1e9;
            double memUsedGb = (mi.totalMem - mi.availMem) / 1e9;
            JSObject mem = new JSObject();
            mem.put("total_gb", round1(memTotalGb));
            mem.put("used_gb", round1(memUsedGb));
            mem.put("usage_pct", memTotalGb > 0 ? Math.round(memUsedGb / memTotalGb * 100) : 0);
            out.put("memory", mem);

            StatFs st = new StatFs(Environment.getDataDirectory().getPath());
            double diskTotalGb = st.getTotalBytes() / 1e9;
            double diskUsedGb = (st.getTotalBytes() - st.getAvailableBytes()) / 1e9;
            JSObject disk = new JSObject();
            disk.put("total_gb", round1(diskTotalGb));
            disk.put("used_gb", round1(diskUsedGb));
            disk.put("usage_pct", diskTotalGb > 0 ? Math.round(diskUsedGb / diskTotalGb * 100) : 0);
            out.put("disk", disk);

            Intent bi = getContext().registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
            if (bi != null) {
                int level = bi.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int scale = bi.getIntExtra(BatteryManager.EXTRA_SCALE, 100);
                int status = bi.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                int tenthsC = bi.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Integer.MIN_VALUE);
                JSObject bat = new JSObject();
                if (level >= 0 && scale > 0) bat.put("level_pct", Math.round(level * 100f / scale));
                bat.put("charging", status == BatteryManager.BATTERY_STATUS_CHARGING
                        || status == BatteryManager.BATTERY_STATUS_FULL);
                if (tenthsC != Integer.MIN_VALUE) bat.put("temp_c", round1(tenthsC / 10.0));
                out.put("battery", bat);
            }

            JSObject cpu = new JSObject();
            cpu.put("cores_logical", Runtime.getRuntime().availableProcessors());
            out.put("cpu", cpu);

            long up = android.os.SystemClock.elapsedRealtime() / 1000;
            out.put("uptime", (up / 3600) + "h " + ((up % 3600) / 60) + "m");
            call.resolve(out);
        } catch (Exception e) {
            call.reject("Could not read device stats: " + e.getMessage());
        }
    }

    private static double round1(double v) {
        return Math.round(v * 10) / 10.0;
    }

    /** Asks for permission to send texts. Each text still needs a Send tap. */
    @PluginMethod
    public void requestTextPermission(PluginCall call) {
        if (getPermissionState("sms") == PermissionState.GRANTED) {
            call.resolve(result("sms", "granted"));
            return;
        }
        requestPermissionForAlias("sms", call, "smsPermissionCallback");
    }

    @PermissionCallback
    private void smsPermissionCallback(PluginCall call) {
        boolean granted = getPermissionState("sms") == PermissionState.GRANTED;
        call.resolve(result("sms", granted ? "granted" : "denied"));
    }

    private static String normalise(String value) {
        if (value == null) return null;
        String v = value.trim().toLowerCase();
        return v.isEmpty() ? null : v;
    }

    private static String clip(String value, int max) {
        if (value == null) return null;
        return value.length() > max ? value.substring(0, max) : value;
    }

    private static JSObject result(String detail, String status) {
        JSObject obj = new JSObject();
        obj.put("status", status);
        obj.put("detail", detail);
        return obj;
    }
}
