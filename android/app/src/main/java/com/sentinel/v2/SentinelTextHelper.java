package com.sentinel.v2;

import android.content.Context;
import android.database.Cursor;
import android.os.Build;
import android.provider.ContactsContract;
import android.telephony.SmsManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Contact lookup, contact sync to the PC, and sending texts for Sentinel.
 * Nothing here runs on its own: a sync happens when Thomas taps Sync contacts,
 * and a text is sent only after he taps Send on the draft notification.
 */
final class SentinelTextHelper {

    static final class Contact {
        final String name;
        final String number;

        Contact(String name, String number) {
            this.name = name;
            this.number = number;
        }
    }

    private SentinelTextHelper() {}

    /** Every contact that has at least one phone number, grouped by name. */
    static Map<String, List<String>> readAllContacts(Context ctx) {
        Map<String, List<String>> out = new LinkedHashMap<>();
        Cursor c = ctx.getContentResolver().query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            new String[] {
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME_PRIMARY,
                ContactsContract.CommonDataKinds.Phone.NUMBER
            },
            null, null, null);
        if (c == null) return out;
        try {
            while (c.moveToNext()) {
                String name = c.getString(0);
                String number = c.getString(1);
                if (name == null || name.trim().isEmpty()) continue;
                if (number == null || number.trim().isEmpty()) continue;
                List<String> numbers = out.get(name);
                if (numbers == null) {
                    numbers = new ArrayList<>();
                    out.put(name, numbers);
                }
                if (!numbers.contains(number)) numbers.add(number);
            }
        } finally {
            c.close();
        }
        return out;
    }

    /**
     * Exact name match only. The PC has already resolved nicknames and checked blocks,
     * so the name it sends is the one to find here. If it is gone, the caller reports it.
     */
    static Contact findContact(Context ctx, String exactName) {
        if (exactName == null || exactName.trim().isEmpty()) return null;
        Map<String, List<String>> all = readAllContacts(ctx);
        List<String> numbers = all.get(exactName);
        if (numbers == null || numbers.isEmpty()) return null;
        return new Contact(exactName, numbers.get(0));
    }

    /** Sends the full contact list (names and numbers) to the PC backend. Returns the number of contacts sent. */
    static int syncToPc(Context ctx, String backend, String apiKey) throws Exception {
        Map<String, List<String>> all = readAllContacts(ctx);
        JSONArray list = new JSONArray();
        for (Map.Entry<String, List<String>> e : all.entrySet()) {
            JSONObject item = new JSONObject();
            item.put("name", e.getKey());
            item.put("numbers", new JSONArray(e.getValue()));
            list.put(item);
        }
        JSONObject body = new JSONObject();
        body.put("contacts", list);

        HttpURLConnection c = (HttpURLConnection) new URL(backend + "/phone/contacts").openConnection();
        try {
            c.setConnectTimeout(5000);
            c.setReadTimeout(15000);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            c.setRequestProperty("X-Api-Key", apiKey);
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream os = c.getOutputStream()) {
                os.write(bytes);
            }
            int code = c.getResponseCode();
            if (code != 200) throw new IllegalStateException("http_" + code);
            return all.size();
        } finally {
            c.disconnect();
        }
    }

    /** Sends one text. Returns false if the SMS permission is missing or the send fails. */
    static boolean sendSms(Context ctx, String number, String message) {
        if (number == null || number.isEmpty() || message == null || message.isEmpty()) return false;
        try {
            SmsManager sms = Build.VERSION.SDK_INT >= 31
                ? ctx.getSystemService(SmsManager.class)
                : SmsManager.getDefault();
            if (sms == null) return false;
            ArrayList<String> parts = sms.divideMessage(message);
            if (parts.size() == 1) {
                sms.sendTextMessage(number, null, message, null, null);
            } else {
                sms.sendMultipartTextMessage(number, null, parts, null, null);
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
