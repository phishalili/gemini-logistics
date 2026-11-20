package eu.geminilogistics.app;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.PowerManager;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.view.View;
import android.view.Window;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
  static final String LIVE = "https://phishalili.github.io/gemini-logistics/";
  static final String LIVE_HOST = "phishalili.github.io";
  static final String OFFLINE = "file:///android_asset/www/index.html";
  static final int REQ_FILE = 11, REQ_GEO = 12, REQ_NOTIF = 13;

  WebView web;
  boolean usingOffline = false;
  ValueCallback<Uri[]> fileCb;
  GeolocationPermissions.Callback geoCb;
  String geoOrigin;

  static final String DL_JS = "(function(){if(window.__gd)return;window.__gd=1;var c=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){if(this.download&&this.href.indexOf('blob:')===0){var n=this.download;fetch(this.href).then(function(r){return r.blob()}).then(function(b){var fr=new FileReader();fr.onload=function(){var s=String(fr.result);GeminiAndroid.saveFile64(n,b.type||'',s.substring(s.indexOf(',')+1))};fr.readAsDataURL(b)});return;}return c.call(this)};})()";

  @Override protected void onCreate(Bundle b) {
    super.onCreate(b);
    Window w = getWindow();
    w.setStatusBarColor(Color.WHITE);
    w.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
    web = new WebView(this);
    setContentView(web);
    WebSettings s = web.getSettings();
    s.setJavaScriptEnabled(true);
    s.setDomStorageEnabled(true);
    s.setDatabaseEnabled(true);
    s.setGeolocationEnabled(true);
    s.setAllowFileAccess(true);
    s.setMediaPlaybackRequiresUserGesture(false);
    s.setCacheMode(WebSettings.LOAD_DEFAULT);
    s.setUserAgentString(s.getUserAgentString() + " GeminiApp/2.4");
    web.addJavascriptInterface(new Bridge(), "GeminiAndroid");
    web.setWebViewClient(new WebViewClient() {
      @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
        Uri u = r.getUrl();
        if (isOwn(u)) return false;
        openExternal(u);
        return true;
      }
      @Override public void onPageFinished(WebView v, String url) { v.evaluateJavascript(DL_JS, null); }
      @Override public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
        if (r.isForMainFrame() && !usingOffline) {
          usingOffline = true;
          toast("Pa internet: po hapet kopja në telefon");
          v.loadUrl(OFFLINE);
        }
      }
    });
    web.setWebChromeClient(new WebChromeClient() {
      @Override public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback cb) {
        if (hasLocation()) { cb.invoke(origin, true, false); return; }
        geoCb = cb; geoOrigin = origin;
        requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION}, REQ_GEO);
      }
      @Override public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
        if (fileCb != null) fileCb.onReceiveValue(null);
        fileCb = cb;
        Intent i = new Intent(Intent.ACTION_GET_CONTENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        try { startActivityForResult(Intent.createChooser(i, "Zgjidh skedarin"), REQ_FILE); }
        catch (ActivityNotFoundException e) { fileCb = null; return false; }
        return true;
      }
    });
    if (b != null) web.restoreState(b);
    else if (online()) web.loadUrl(LIVE);
    else { usingOffline = true; toast("Pa internet: po hapet kopja në telefon"); web.loadUrl(OFFLINE); }
    if (!NotifyService.topic(this).isEmpty()) NotifyService.start(this);
  }

  boolean isOwn(Uri u) {
    String sc = u.getScheme();
    if ("file".equals(sc) || "blob".equals(sc) || "data".equals(sc) || "about".equals(sc)) return true;
    return "https".equals(sc) && LIVE_HOST.equals(u.getHost()) && u.getPath() != null && u.getPath().startsWith("/gemini-logistics");
  }

  void openExternal(Uri u) {
    String sc = u.getScheme() == null ? "" : u.getScheme();
    try {
      if (sc.equals("tel")) { startActivity(new Intent(Intent.ACTION_DIAL, u)); return; }
      Intent i = new Intent(Intent.ACTION_VIEW, u);
      i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
      startActivity(i);
    } catch (ActivityNotFoundException e) {
      if (sc.equals("viber")) toast("Viber nuk është i instaluar në telefon");
      else if (sc.equals("whatsapp") || "wa.me".equals(u.getHost())) toast("WhatsApp nuk u hap");
      else toast("Nuk u hap: " + u);
    }
  }

  boolean online() {
    ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
    if (cm == null || cm.getActiveNetwork() == null) return false;
    NetworkCapabilities c = cm.getNetworkCapabilities(cm.getActiveNetwork());
    return c != null && c.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
  }

  boolean hasLocation() {
    return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
  }

  void toast(String t) { runOnUiThread(() -> Toast.makeText(this, t, Toast.LENGTH_LONG).show()); }

  @Override public void onRequestPermissionsResult(int req, String[] p, int[] g) {
    if (req == REQ_GEO && geoCb != null) { geoCb.invoke(geoOrigin, hasLocation(), false); geoCb = null; }
    if (req == REQ_NOTIF) { askBattery(); NotifyService.start(this); }
  }

  @Override protected void onActivityResult(int req, int res, Intent data) {
    if (req == REQ_FILE && fileCb != null) {
      Uri[] r = null;
      if (res == RESULT_OK && data != null && data.getData() != null) r = new Uri[]{data.getData()};
      fileCb.onReceiveValue(r);
      fileCb = null;
    }
  }

  @Override protected void onSaveInstanceState(Bundle o) { super.onSaveInstanceState(o); web.saveState(o); }

  @Override public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }

  void askNotifications() {
    if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
      requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIF);
    } else { askBattery(); NotifyService.start(this); }
  }

  // Që Android të mos e ndalë dëgjimin e njoftimeve kur telefoni fle
  void askBattery() {
    SharedPreferences sp = getSharedPreferences(NotifyService.PREFS, MODE_PRIVATE);
    if (sp.getBoolean("askedBattery", false)) return;
    sp.edit().putBoolean("askedBattery", true).apply();
    PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
    if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
      try {
        Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName()));
        startActivity(i);
      } catch (Exception ignored) {}
    }
  }

  Uri saveBytes(String name, String mime, byte[] data) throws Exception {
    if (Build.VERSION.SDK_INT >= 29) {
      ContentValues v = new ContentValues();
      v.put(MediaStore.Downloads.DISPLAY_NAME, name);
      v.put(MediaStore.Downloads.MIME_TYPE, mime.isEmpty() ? "application/octet-stream" : mime);
      v.put(MediaStore.Downloads.IS_PENDING, 1);
      Uri u = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
      if (u == null) throw new Exception("insert");
      try (OutputStream os = getContentResolver().openOutputStream(u)) { os.write(data); }
      v.clear(); v.put(MediaStore.Downloads.IS_PENDING, 0);
      getContentResolver().update(u, v, null, null);
      return u;
    } else {
      File d = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
      d.mkdirs();
      File f = new File(d, name);
      try (FileOutputStream os = new FileOutputStream(f)) { os.write(data); }
      return null;
    }
  }

  class Bridge {
    @JavascriptInterface public void saveFile64(String name, String mime, String b64) {
      try {
        byte[] data = Base64.decode(b64, Base64.DEFAULT);
        Uri u = saveBytes(name, mime == null ? "" : mime, data);
        boolean pdf = name.toLowerCase().endsWith(".pdf") || "application/pdf".equals(mime);
        if (pdf && u != null) {
          Intent s = new Intent(Intent.ACTION_SEND);
          s.setType("application/pdf");
          s.putExtra(Intent.EXTRA_STREAM, u);
          s.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
          runOnUiThread(() -> startActivity(Intent.createChooser(s, "Dërgo PDF-në")));
          toast("U ruajt te Downloads: " + name);
        } else if (name.toLowerCase().endsWith(".json")) toast("Kopja u ruajt te Downloads: " + name);
        else toast("U ruajt te Downloads: " + name);
      } catch (Exception e) { toast("Skedari nuk u ruajt"); }
    }
    @JavascriptInterface public void saveFile(String name, String mime, String text) {
      saveFile64(name, mime, Base64.encodeToString(text.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP));
    }
    @JavascriptInterface public void setNotify(String topic, String dev, String user) {
      Context c = MainActivity.this;
      String old = NotifyService.topic(c);
      SharedPreferences.Editor ed = c.getSharedPreferences(NotifyService.PREFS, MODE_PRIVATE).edit();
      if (topic == null || !topic.trim().equals(old)) ed.remove("since");
      ed
          .putString("topic", topic == null ? "" : topic.trim())
          .putString("dev", dev == null ? "" : dev)
          .putString("user", user == null ? "" : user).apply();
      runOnUiThread(() -> {
        if (topic == null || topic.trim().isEmpty()) NotifyService.stop(c);
        else if (!topic.trim().equals(old)) { NotifyService.restart(c); askNotifications(); }
        else askNotifications();
      });
    }
    @JavascriptInterface public String version() { return "2.4"; }
  }
}
