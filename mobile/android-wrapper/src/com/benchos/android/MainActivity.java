package com.benchos.android;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.net.URI;
import java.net.URISyntaxException;

public final class MainActivity extends Activity {
    private static final int PICK_FILE = 1;
    private static final String LOCAL_URL = "http://localhost:3000";
    private static final int INK = Color.rgb(23, 36, 57);
    private static final int PRIMARY = Color.rgb(67, 56, 202);
    private static final int SURFACE = Color.rgb(245, 247, 251);

    private SharedPreferences preferences;
    private URI server;
    private FrameLayout content;
    private WebView browser;
    private ValueCallback<Uri[]> fileResult;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        preferences = getSharedPreferences("connection", MODE_PRIVATE);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(SURFACE);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                Insets keyboard = insets.getInsets(WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, keyboard.bottom));
            }
            return insets;
        });
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            getWindow().getInsetsController().setSystemBarsAppearance(
                android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                    | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
                android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                    | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            );
        }

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(16), 0, dp(8), 0);
        toolbar.setBackgroundColor(Color.WHITE);
        TextView logo = label("AspireOs", 20, PRIMARY);
        logo.setTypeface(null, android.graphics.Typeface.BOLD);
        toolbar.addView(logo, new LinearLayout.LayoutParams(0, -2, 1));
        Button settings = new Button(this, null, android.R.attr.borderlessButtonStyle);
        settings.setText("Server");
        settings.setContentDescription("Change server address");
        settings.setOnClickListener(view -> showConnection(null));
        toolbar.addView(settings);
        root.addView(toolbar, new LinearLayout.LayoutParams(-1, dp(52)));
        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);

        server = serverAddress(preferences.getString("server", ""));
        if (server == null) showConnection(null);
        else openServer(server);
    }

    private void showConnection(String error) {
        if (browser != null) browser.setVisibility(View.GONE);
        View previous = content.findViewWithTag("connection");
        if (previous != null) content.removeView(previous);

        android.widget.ScrollView scroll = new android.widget.ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setTag("connection");
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setGravity(Gravity.CENTER_VERTICAL);
        form.setPadding(dp(24), dp(24), dp(24), dp(24));
        scroll.addView(form);
        TextView title = label(error == null ? "Connect to AspireOs" : "Couldn’t reach AspireOs", 25, INK);
        title.setTypeface(null, android.graphics.Typeface.BOLD);
        form.addView(title);
        addText(form, error == null
            ? "Enter the AspireOs website address your administrator gave you. For a local USB demo, use the option below."
            : error, 16, INK, 10);
        EditText address = new EditText(this);
        address.setSingleLine(true);
        address.setHint("https://aspireos.example.com");
        address.setContentDescription("AspireOs website address");
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        if (server != null) address.setText(server.toString());
        form.addView(address, spaced(16));

        Button connect = new Button(this);
        connect.setText("Connect");
        connect.setOnClickListener(view -> {
            URI destination = serverAddress(address.getText().toString());
            if (destination == null) {
                address.setError("Enter an HTTPS website address, or use the local USB demo.");
                address.requestFocus();
            } else {
                ((android.view.inputmethod.InputMethodManager) getSystemService(INPUT_METHOD_SERVICE))
                    .hideSoftInputFromWindow(address.getWindowToken(), 0);
                openServer(destination);
            }
        });
        form.addView(connect, spaced(12));
        Button local = new Button(this, null, android.R.attr.borderlessButtonStyle);
        local.setText("Use local USB demo");
        local.setOnClickListener(view -> openServer(URI.create(LOCAL_URL)));
        form.addView(local, spaced(6));
        content.addView(scroll);
    }

    private static URI serverAddress(String value) {
        String address = value.trim();
        if (address.isEmpty()) return null;
        if (!address.contains("://")) address = "https://" + address;
        try {
            URI parsed = new URI(address);
            String host = parsed.getHost();
            String scheme = parsed.getScheme().toLowerCase(java.util.Locale.ROOT);
            if (host == null || parsed.getRawUserInfo() != null || parsed.getPort() > 65535) return null;
            if (!"https".equals(scheme) && !("http".equals(scheme)
                    && ("localhost".equalsIgnoreCase(host) || "127.0.0.1".equals(host) || "10.0.2.2".equals(host)))) {
                return null;
            }
            return new URI(scheme, null, host, parsed.getPort(), null, null, null);
        } catch (URISyntaxException e) {
            return null;
        }
    }

    private static int port(Uri url) {
        return url.getPort() != -1 ? url.getPort() : "https".equalsIgnoreCase(url.getScheme()) ? 443 : 80;
    }

    private boolean isServer(Uri url) {
        Uri base = Uri.parse(server.toString());
        return base.getScheme().equalsIgnoreCase(url.getScheme())
            && base.getHost().equalsIgnoreCase(url.getHost()) && port(base) == port(url)
            && url.getUserInfo() == null;
    }

    private void openServer(URI address) {
        server = address;
        preferences.edit().putString("server", address.toString()).apply();
        content.removeAllViews();
        if (browser != null) browser.destroy();
        browser = new WebView(this);
        browser.getSettings().setJavaScriptEnabled(true);
        browser.getSettings().setDomStorageEnabled(true);
        browser.getSettings().setAllowFileAccess(false);
        browser.getSettings().setAllowContentAccess(false);
        browser.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        browser.getSettings().setJavaScriptCanOpenWindowsAutomatically(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(browser, false);

        browser.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                if (isServer(url)) return false;
                if (request.isForMainFrame() && request.hasGesture() && "https".equalsIgnoreCase(url.getScheme())) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, url));
                    } catch (ActivityNotFoundException ignored) {
                        Toast.makeText(MainActivity.this, "No browser is available to open this link.", Toast.LENGTH_SHORT).show();
                    }
                }
                return true;
            }

            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showConnection(connectionHelp());
            }

            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse error) {
                if (request.isForMainFrame() && error.getStatusCode() >= 400) showConnection(connectionHelp());
            }
        });
        browser.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileResult != null) fileResult.onReceiveValue(null);
                fileResult = callback;
                try {
                    startActivityForResult(params.createIntent(), PICK_FILE);
                } catch (ActivityNotFoundException ignored) {
                    fileResult.onReceiveValue(null);
                    fileResult = null;
                }
                return true;
            }
        });
        browser.setDownloadListener((url, userAgent, disposition, mimeType, length) -> {
            Uri download = Uri.parse(url);
            if (!isServer(download)) return;
            String filename = URLUtil.guessFileName(url, disposition, mimeType).replaceAll("[/\\\\]", "_");
            try {
                DownloadManager.Request request = new DownloadManager.Request(download)
                    .setTitle(filename)
                    .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);
                if (mimeType != null) request.setMimeType(mimeType);
                String cookie = CookieManager.getInstance().getCookie(url);
                if (cookie != null) request.addRequestHeader("Cookie", cookie);
                ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(request);
            } catch (RuntimeException e) {
                Toast.makeText(this, "Download unavailable. Try again from AspireOs.", Toast.LENGTH_LONG).show();
            }
        });
        content.addView(browser, new FrameLayout.LayoutParams(-1, -1));
        browser.loadUrl(server.toString());
    }

    private String connectionHelp() {
        return "Check that the AspireOs address is correct and the server is running. For the local demo, connect your phone by USB and forward ports 3000 and 8000 with adb.";
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_FILE && fileResult != null) {
            fileResult.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileResult = null;
        }
    }

    @Override public void onBackPressed() {
        View form = content.findViewWithTag("connection");
        if (form != null && browser != null && browser.getUrl() != null) {
            content.removeView(form);
            browser.setVisibility(View.VISIBLE);
        } else if (browser != null && browser.canGoBack()) {
            browser.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override protected void onDestroy() {
        if (fileResult != null) fileResult.onReceiveValue(null);
        if (browser != null) {
            content.removeView(browser);
            browser.destroy();
        }
        super.onDestroy();
    }

    private TextView label(String text, int size, int color) {
        TextView label = new TextView(this);
        label.setText(text);
        label.setTextSize(size);
        label.setTextColor(color);
        return label;
    }

    private void addText(LinearLayout parent, String text, int size, int color, int top) {
        parent.addView(label(text, size, color), spaced(top));
    }

    private LinearLayout.LayoutParams spaced(int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(top);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
