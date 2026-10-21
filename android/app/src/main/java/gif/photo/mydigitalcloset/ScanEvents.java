package gif.photo.mydigitalcloset;

import android.webkit.WebView;
import java.lang.ref.WeakReference;
import org.json.JSONObject;

/** Tells the page when the phone is plugged in, unplugged, or needs to look again. */
final class ScanEvents {
    private static WeakReference<MainActivity> activity = new WeakReference<>(null);

    private ScanEvents() {}

    static void attach(MainActivity value) {
        activity = new WeakReference<>(value);
    }

    static void emit(String name) {
        MainActivity current = activity.get();
        if (current == null) return;
        current.runOnUiThread(() -> {
            if (current.getBridge() == null) return;
            WebView webView = current.getBridge().getWebView();
            if (webView == null) return;
            webView.onResume();
            webView.resumeTimers();
            webView.evaluateJavascript("window.onClosetScan&&window.onClosetScan(" + JSONObject.quote(name) + ")", null);
        });
    }
}
