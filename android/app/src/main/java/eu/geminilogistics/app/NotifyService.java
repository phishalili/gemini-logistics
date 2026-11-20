package eu.geminilogistics.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

// Dëgjon temën e njoftimeve (ntfy.sh) dhe shfaq njoftim për çdo porosi të re, edhe kur app-i është i mbyllur
public class NotifyService extends Service {
  static final String PREFS = "gemini.notify";
  static final String CH_ORDERS = "orders", CH_SVC = "svc";
  volatile boolean running = false;
  volatile HttpURLConnection conn;
  Thread worker;

  static String topic(Context c) { return c.getSharedPreferences(PREFS, MODE_PRIVATE).getString("topic", ""); }

  static void start(Context c) {
    if (topic(c).isEmpty()) return;
    Intent i = new Intent(c, NotifyService.class);
    try { if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i); else c.startService(i); } catch (Exception ignored) {}
  }
  static void stop(Context c) { c.stopService(new Intent(c, NotifyService.class)); }
  static void restart(Context c) { stop(c); start(c); }

  static void channels(Context c) {
    if (Build.VERSION.SDK_INT < 26) return;
    NotificationManager nm = c.getSystemService(NotificationManager.class);
    NotificationChannel o = new NotificationChannel(CH_ORDERS, "Porositë e reja", NotificationManager.IMPORTANCE_HIGH);
    o.setDescription("Njoftim kur shtohet një porosi ose veturë e re");
    nm.createNotificationChannel(o);
    NotificationChannel s = new NotificationChannel(CH_SVC, "Lidhja për njoftime", NotificationManager.IMPORTANCE_MIN);
    s.setDescription("Mban app-in të lidhur që njoftimet të vijnë menjëherë");
    s.setShowBadge(false);
    nm.createNotificationChannel(s);
  }

  PendingIntent openApp() {
    Intent i = new Intent(this, MainActivity.class);
    i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    return PendingIntent.getActivity(this, 0, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
  }

  Notification.Builder builder(String ch) {
    return Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, ch) : new Notification.Builder(this);
  }

  @Override public int onStartCommand(Intent intent, int flags, int startId) {
    channels(this);
    Notification n = builder(CH_SVC).setSmallIcon(R.drawable.ic_stat).setContentTitle("Gemini Logistics")
        .setContentText("Njoftimet për porositë e reja janë aktive").setOngoing(true).setContentIntent(openApp()).build();
    try {
      if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING);
      else startForeground(1, n);
    } catch (Exception e) { stopSelf(); return START_NOT_STICKY; }
    if (topic(this).isEmpty()) { stopSelf(); return START_NOT_STICKY; }
    if (!running) { running = true; worker = new Thread(this::loop, "ntfy"); worker.start(); }
    return START_STICKY;
  }

  void loop() {
    long wait = 3000;
    while (running) {
      SharedPreferences sp = getSharedPreferences(PREFS, MODE_PRIVATE);
      String t = sp.getString("topic", ""), dev = sp.getString("dev", ""), since = sp.getString("since", "");
      if (t.isEmpty()) { stopSelf(); return; }
      try {
        String u = "https://ntfy.sh/" + Uri.encode(t) + "/json" + (since.isEmpty() ? "" : "?since=" + Uri.encode(since));
        HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection();
        conn = c;
        c.setConnectTimeout(15000);
        c.setReadTimeout(120000);
        c.setRequestProperty("User-Agent", "GeminiLogistics/2.4");
        BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
        wait = 3000;
        String line;
        while (running && (line = r.readLine()) != null) {
          if (line.isEmpty()) continue;
          JSONObject j = new JSONObject(line);
          if (!"message".equals(j.optString("event"))) continue;
          String id = j.optString("id");
          sp.edit().putString("since", id).apply();
          JSONArray tags = j.optJSONArray("tags");
          boolean own = false;
          if (tags != null && !dev.isEmpty()) for (int i = 0; i < tags.length(); i++) if (("dev-" + dev).equals(tags.optString(i))) own = true;
          if (!own) show(j.optString("title", "Gemini Logistics"), j.optString("message", ""), id);
        }
        r.close();
      } catch (Exception e) {
        // pa internet ose lidhja ra: provo prapë pak më vonë
      }
      if (!running) break;
      try { Thread.sleep(wait); } catch (InterruptedException ie) { break; }
      wait = Math.min(wait * 2, 60000);
    }
  }

  void show(String title, String msg, String id) {
    NotificationManager nm = getSystemService(NotificationManager.class);
    Notification n = builder(CH_ORDERS).setSmallIcon(R.drawable.ic_stat).setContentTitle(title.isEmpty() ? "Gemini Logistics" : title)
        .setContentText(msg).setStyle(new Notification.BigTextStyle().bigText(msg)).setAutoCancel(true)
        .setContentIntent(openApp()).setPriority(Notification.PRIORITY_HIGH).setDefaults(Notification.DEFAULT_ALL).build();
    nm.notify(id.hashCode(), n);
  }

  @Override public void onDestroy() {
    running = false;
    try { if (conn != null) conn.disconnect(); } catch (Exception ignored) {}
    if (worker != null) worker.interrupt();
    super.onDestroy();
  }

  @Override public IBinder onBind(Intent i) { return null; }
}
