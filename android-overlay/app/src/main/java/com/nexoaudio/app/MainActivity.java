package com.nexoaudio.app;

import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;
import org.json.JSONArray;

public class MainActivity extends BridgeActivity {
    private boolean nativeBridgeAdded = false;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        configureWebView();
    }

    @Override
    public void onStart() {
        super.onStart();
        configureWebView();
    }

    private void configureWebView() {
        if (this.bridge == null || this.bridge.getWebView() == null) {
            return;
        }
        WebView webView = this.bridge.getWebView();
        WebSettings settings = webView.getSettings();
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        if (!nativeBridgeAdded) {
            webView.addJavascriptInterface(new NexoNativeBridge(), "NexoNative");
            nativeBridgeAdded = true;
        }
    }

    public static class NexoNativeBridge {
        private static Set<String> collectSubnets() {
            Set<String> prefixes = new LinkedHashSet<>();
            try {
                for (NetworkInterface nif : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                    if (!nif.isUp() || nif.isLoopback()) continue;
                    for (InetAddress addr : Collections.list(nif.getInetAddresses())) {
                        if (addr instanceof Inet4Address && !addr.isLoopbackAddress()) {
                            String ip = addr.getHostAddress();
                            if (ip != null && !ip.startsWith("169.254.") && !ip.startsWith("100.")) {
                                int lastDot = ip.lastIndexOf('.');
                                if (lastDot > 0) {
                                    prefixes.add(ip.substring(0, lastDot));
                                }
                            }
                        }
                    }
                }
            } catch (Exception ignored) {}
            return prefixes;
        }

        @JavascriptInterface
        public String getLocalSubnets() {
            return new JSONArray(collectSubnets()).toString();
        }

        @JavascriptInterface
        public String discoverServer(int port, int timeoutMs) {
            DatagramSocket socket = null;
            try {
                socket = new DatagramSocket();
                socket.setBroadcast(true);
                socket.setSoTimeout(Math.max(150, Math.min(timeoutMs, 1500)));

                byte[] payload = "NEXOAUDIO_DISCOVER".getBytes("UTF-8");

                try {
                    socket.send(new DatagramPacket(payload, payload.length, InetAddress.getByName("255.255.255.255"), port));
                } catch (Exception ignored) {}

                for (String prefix : collectSubnets()) {
                    try {
                        socket.send(new DatagramPacket(payload, payload.length, InetAddress.getByName(prefix + ".255"), port));
                        socket.send(new DatagramPacket(payload, payload.length, InetAddress.getByName(prefix + ".1"), port));
                    } catch (Exception ignored) {}
                }

                try {
                    socket.send(new DatagramPacket(payload, payload.length, InetAddress.getByName("192.168.137.1"), port));
                    socket.send(new DatagramPacket(payload, payload.length, InetAddress.getByName("192.168.43.1"), port));
                } catch (Exception ignored) {}

                byte[] buf = new byte[512];
                DatagramPacket recv = new DatagramPacket(buf, buf.length);
                while (true) {
                    socket.receive(recv);
                    String msg = new String(recv.getData(), 0, recv.getLength(), "UTF-8");
                    if (msg.contains("nexoaudio")) {
                        String host = recv.getAddress().getHostAddress();
                        if (host != null && !host.isEmpty()) {
                            return host;
                        }
                    }
                }
            } catch (Exception ignored) {
            } finally {
                if (socket != null) {
                    try { socket.close(); } catch (Exception ignored) {}
                }
            }
            return "";
        }
    }
}
