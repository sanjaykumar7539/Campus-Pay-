package edu.campuspay.hardware;
import android.content.*;
import android.os.*;
import net.posprinter.service.PosprinterService;

public class VendorPrinterService extends PosprinterService {
 private Context guarded;
 @Override public Context getApplicationContext(){if(guarded==null)guarded=new PrinterContext(super.getApplicationContext());return guarded;}
 @Override public Intent registerReceiver(BroadcastReceiver receiver,IntentFilter filter){
  return Build.VERSION.SDK_INT>=33?super.registerReceiver(receiver,filter,PrinterContext.flags(filter)):super.registerReceiver(receiver,filter);
 }
 @Override public Intent registerReceiver(BroadcastReceiver receiver,IntentFilter filter,String permission,Handler handler){
  return Build.VERSION.SDK_INT>=33?super.registerReceiver(receiver,filter,permission,handler,PrinterContext.flags(filter)):super.registerReceiver(receiver,filter,permission,handler);
 }
}
