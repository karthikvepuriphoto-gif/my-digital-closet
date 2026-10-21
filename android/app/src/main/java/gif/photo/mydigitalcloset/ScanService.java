package gif.photo.mydigitalcloset;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ServiceInfo;
import android.os.BatteryManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

/** Keeps a closet scan running when the app is not on screen, and shows its progress. */
public class ScanService extends Service {
    public static final String ACTION_START = "gif.photo.mydigitalcloset.SCAN_START";
    public static final String ACTION_UPDATE = "gif.photo.mydigitalcloset.SCAN_UPDATE";
    public static final String ACTION_CHARGER = "gif.photo.mydigitalcloset.SCAN_CHARGER";
    public static final String ACTION_STOP = "gif.photo.mydigitalcloset.SCAN_STOP";

    private static final int NOTIFICATION_ID = 42;
    private static final String CHANNEL_ID = "closet-scan";
    private static volatile boolean active = false;

    private PowerManager.WakeLock wakeLock;
    private BroadcastReceiver powerReceiver;
    private boolean receiverRegistered = false;
    private boolean stopped = false;

    public static boolean isActive() {
        return active;
    }

    public static boolean onPower(Context context) {
        Intent battery = context.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (battery == null) return false;
        int plugged = battery.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0);
        return plugged != 0;
    }

    public static String thermal(Context context) {
        if (Build.VERSION.SDK_INT < 29) return "ok";
        PowerManager manager = (PowerManager) context.getSystemService(POWER_SERVICE);
        if (manager == null) return "ok";
        int status = manager.getCurrentThermalStatus();
        if (status >= PowerManager.THERMAL_STATUS_SEVERE) return "hot";
        return "ok";
    }

    public static void launch(Context context, String action, String body, int done, int total) {
        Intent intent = new Intent(context, ScanService.class);
        intent.setAction(action);
        intent.putExtra("body", body);
        intent.putExtra("done", done);
        intent.putExtra("total", total);
        if (ACTION_STOP.equals(action)) {
            context.startService(intent);
            return;
        }
        ContextCompat.startForegroundService(context, intent);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || ACTION_STOP.equals(intent.getAction())) {
            shutdown();
            return START_NOT_STICKY;
        }
        String body = intent.getStringExtra("body");
        if (body == null || body.isEmpty()) body = "Scanning photos";
        int done = intent.getIntExtra("done", 0);
        int total = intent.getIntExtra("total", 0);
        Notification notification = buildNotification(body, done, total);
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
        active = true;
        stopped = false;
        ensureReceiver();
        if (ACTION_CHARGER.equals(intent.getAction())) releaseLock();
        else acquireLock();
        return START_NOT_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        shutdown();
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        active = false;
        releaseLock();
        unregisterPower();
        super.onDestroy();
    }

    private void shutdown() {
        if (stopped) return;
        stopped = true;
        active = false;
        releaseLock();
        unregisterPower();
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    private void ensureReceiver() {
        if (receiverRegistered) return;
        powerReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String action = intent.getAction();
                if (Intent.ACTION_POWER_CONNECTED.equals(action)) {
                    acquireLock();
                    ScanEvents.emit("charging");
                } else if (Intent.ACTION_POWER_DISCONNECTED.equals(action)) {
                    ScanEvents.emit("unplugged");
                }
            }
        };
        IntentFilter filter = new IntentFilter();
        filter.addAction(Intent.ACTION_POWER_CONNECTED);
        filter.addAction(Intent.ACTION_POWER_DISCONNECTED);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(powerReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(powerReceiver, filter);
        }
        receiverRegistered = true;
    }

    private void unregisterPower() {
        if (!receiverRegistered) return;
        try {
            unregisterReceiver(powerReceiver);
        } catch (IllegalArgumentException ignored) {
            /* Already unregistered. */
        }
        receiverRegistered = false;
    }

    private void acquireLock() {
        if (wakeLock == null) {
            PowerManager manager = (PowerManager) getSystemService(POWER_SERVICE);
            if (manager == null) return;
            wakeLock = manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "closet:scan");
            wakeLock.setReferenceCounted(false);
        }
        if (!wakeLock.isHeld()) wakeLock.acquire(6L * 60L * 60L * 1000L);
    }

    private void releaseLock() {
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
    }

    private Notification buildNotification(String body, int done, int total) {
        createChannel();
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pending = PendingIntent.getActivity(
            this,
            0,
            open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_closet)
            .setContentTitle("Closet scan")
            .setContentText(body)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(pending)
            .setPriority(NotificationCompat.PRIORITY_LOW);
        if (total > 0) builder.setProgress(total, Math.min(done, total), false);
        return builder.build();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "Closet scan", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Progress while clothes are scanned on this phone.");
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.createNotificationChannel(channel);
    }
}
