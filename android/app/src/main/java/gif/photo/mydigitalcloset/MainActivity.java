package gif.photo.mydigitalcloset;

import android.os.Bundle;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(ClosetScanPlugin.class);
        super.onCreate(savedInstanceState);
        ScanEvents.attach(this);
    }

    @Override
    public void onResume() {
        super.onResume();
        ScanEvents.attach(this);
    }

    @Override
    public void onPause() {
        super.onPause();
        keepScanAlive();
    }

    @Override
    public void onStop() {
        super.onStop();
        keepScanAlive();
    }

    private void keepScanAlive() {
        if (!ScanService.isActive() || bridge == null || bridge.getWebView() == null) return;
        WebView webView = bridge.getWebView();
        webView.onResume();
        webView.resumeTimers();
    }
}
