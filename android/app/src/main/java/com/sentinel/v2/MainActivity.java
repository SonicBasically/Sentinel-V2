package com.sentinel.v2;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(SentinelPhonePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
