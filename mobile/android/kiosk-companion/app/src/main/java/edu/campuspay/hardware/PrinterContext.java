package edu.campuspay.hardware;
import android.content.*;
import android.os.*;

/** Adapts legacy vendor receiver registration to Android 13+ explicit flags. */
final class PrinterContext extends ContextWrapper {
 PrinterContext(Context base){super(base);}
 static int flags(IntentFilter filter){
  // Bluetooth FOUND is a protected framework broadcast sent by the privileged Bluetooth app.
  return filter.countActions()==1&&filter.hasAction("android.bluetooth.device.action.FOUND")?Context.RECEIVER_EXPORTED:Context.RECEIVER_NOT_EXPORTED;
 }
 @Override public Context getApplicationContext(){return this;}
 @Override public Intent registerReceiver(BroadcastReceiver receiver,IntentFilter filter){
  return Build.VERSION.SDK_INT>=33?super.registerReceiver(receiver,filter,flags(filter)):super.registerReceiver(receiver,filter);
 }
 @Override public Intent registerReceiver(BroadcastReceiver receiver,IntentFilter filter,String permission,Handler handler){
  return Build.VERSION.SDK_INT>=33?super.registerReceiver(receiver,filter,permission,handler,flags(filter)):super.registerReceiver(receiver,filter,permission,handler);
 }
}
