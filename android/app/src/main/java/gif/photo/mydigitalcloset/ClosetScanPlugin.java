package gif.photo.mydigitalcloset;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Build;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

@CapacitorPlugin(
    name = "ClosetScan",
    permissions = { @Permission(strings = { Manifest.permission.POST_NOTIFICATIONS }, alias = "notifications") }
)
public class ClosetScanPlugin extends Plugin {
    private String pendingAction = ScanService.ACTION_START;

    @PluginMethod
    public void start(PluginCall call) {
        foreground(call, ScanService.ACTION_START);
    }

    @PluginMethod
    public void update(PluginCall call) {
        foreground(call, ScanService.ACTION_UPDATE);
    }

    @PluginMethod
    public void holdForCharger(PluginCall call) {
        foreground(call, ScanService.ACTION_CHARGER);
    }

    @PluginMethod
    public void resumeWork(PluginCall call) {
        foreground(call, ScanService.ACTION_START);
    }

    @PluginMethod
    public void stop(PluginCall call) {
        try {
            ScanService.launch(getContext(), ScanService.ACTION_STOP, "", 0, 0);
        } catch (Exception ignored) {
            /* The page still has the checkpoint. */
        }
        call.resolve();
    }

    @PluginMethod
    public void status(PluginCall call) {
        JSObject result = new JSObject();
        result.put("known", true);
        result.put("onPower", ScanService.onPower(getContext()));
        result.put("thermal", ScanService.thermal(getContext()));
        call.resolve(result);
    }

    @PermissionCallback
    private void afterPermission(PluginCall call) {
        launch(call, pendingAction);
    }

    private void foreground(PluginCall call, String action) {
        if (needsNotificationPermission()) {
            pendingAction = action;
            requestPermissionForAlias("notifications", call, "afterPermission");
            return;
        }
        launch(call, action);
    }

    private boolean needsNotificationPermission() {
        if (Build.VERSION.SDK_INT < 33) return false;
        return ContextCompat.checkSelfPermission(getContext(), Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED;
    }

    private void launch(PluginCall call, String action) {
        JSObject result = new JSObject();
        try {
            int done = call.getInt("done", 0);
            int total = call.getInt("total", 0);
            ScanService.launch(getContext(), action, call.getString("body", "Scanning photos"), done, total);
            result.put("started", true);
        } catch (Exception ignored) {
            result.put("started", false);
        }
        call.resolve(result);
    }
}
