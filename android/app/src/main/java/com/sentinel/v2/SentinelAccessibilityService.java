package com.sentinel.v2;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.view.accessibility.AccessibilityEvent;

/**
 * Lets Sentinel open an allowed app on an unlocked phone without a tap.
 *
 * Deliberately minimal: it does not read or control the screen
 * (canRetrieveWindowContent=false, no event types). Its only job is to start
 * an activity that SentinelService has already checked against the app allowlist.
 */
public class SentinelAccessibilityService extends AccessibilityService {

    private static volatile SentinelAccessibilityService instance;

    static boolean isEnabled() {
        return instance != null;
    }

    /** Starts the activity if the accessibility service is on. Returns false if it is off. */
    static boolean launch(Intent intent) {
        SentinelAccessibilityService s = instance;
        if (s == null) return false;
        try {
            s.startActivity(intent);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // Intentionally empty: Sentinel does not read screen events.
    }

    @Override
    public void onInterrupt() {
        // Nothing to interrupt.
    }

    @Override
    public boolean onUnbind(Intent intent) {
        instance = null;
        return super.onUnbind(intent);
    }

    @Override
    public void onDestroy() {
        instance = null;
        super.onDestroy();
    }
}
