package edu.campuspay.hardware;
import android.app.*;
import android.os.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import org.json.*;
import net.posprinter.posprinterface.IMyBinder;
import net.posprinter.posprinterface.TaskCallback;
import net.posprinter.service.PosprinterService;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class PrinterWorker extends Service {
 private volatile boolean running=false,connected=false;
 private volatile IMyBinder printer;
 private String origin,token,transport,address;private int port,width;
 private final ExecutorService executor=Executors.newSingleThreadExecutor();
 private final CountDownLatch bound=new CountDownLatch(1);
 private SharedPreferences journal;
 private boolean registered=false;
 private final ServiceConnection connection=new ServiceConnection(){
  public void onServiceConnected(ComponentName n,IBinder b){printer=(IMyBinder)b;bound.countDown();}
  public void onServiceDisconnected(ComponentName n){printer=null;connected=false;}
 };
 @Override public void onCreate(){super.onCreate();journal=getSharedPreferences("print-journal",MODE_PRIVATE);
  NotificationManager manager=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);manager.createNotificationChannel(new NotificationChannel("printer","CampusPay printer",NotificationManager.IMPORTANCE_LOW));
 }
 private Notification notification(String status){return new Notification.Builder(this,"printer").setContentTitle("CampusPay Hardware").setContentText(status).setSmallIcon(android.R.drawable.stat_notify_sync).setOngoing(true).setContentIntent(PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE)).build();}
 private void status(String text){((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(41,notification(text));}
 @Override public int onStartCommand(Intent i,int flags,int startId){
  if(i==null){stopSelf();return START_NOT_STICKY;}
  if(running){status("Already running. Stop before changing printer settings.");return START_NOT_STICKY;}
  origin=i.getStringExtra("origin");token=i.getStringExtra("token");transport=i.getStringExtra("transport");address=i.getStringExtra("address");port=i.getIntExtra("port",9100);width=i.getIntExtra("width",384);
  try{URI u=new URI(origin);if(!"https".equals(u.getScheme())||u.getHost()==null||u.getRawUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||(u.getPath()!=null&&!u.getPath().isEmpty())||token==null||token.length()<32)throw new Exception();}
  catch(Exception e){stopSelf();return START_NOT_STICKY;}
  if(Build.VERSION.SDK_INT>=29)startForeground(41,notification("Starting printer"),ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);else startForeground(41,notification("Starting printer"));
  running=true;registered=bindService(new Intent(this,VendorPrinterService.class),connection,BIND_AUTO_CREATE);
  executor.submit(()->runLoop());return START_NOT_STICKY;
 }
 @Override public IBinder onBind(Intent i){return null;}
 private boolean callback(java.util.function.Consumer<TaskCallback> operation) throws Exception {
  CountDownLatch latch=new CountDownLatch(1);AtomicBoolean success=new AtomicBoolean(false);
  operation.accept(new TaskCallback(){public void OnSucceed(){success.set(true);latch.countDown();}public void OnFailed(){latch.countDown();}});
  return latch.await(15,TimeUnit.SECONDS)&&success.get();
 }
 private boolean connect() throws Exception {if(printer==null)return false;
  if("USB".equals(transport))return callback(cb->printer.ConnectUsbPort(new PrinterContext(getApplicationContext()),address,cb));
  if("Bluetooth".equals(transport))return callback(cb->printer.ConnectBtPort(address,cb));
  if("LAN".equals(transport))return callback(cb->printer.ConnectNetPort(address,port,cb));
  throw new Exception("Unsupported transport");
 }
 private Object api(String path,JSONObject body) throws Exception {
  HttpURLConnection connection=(HttpURLConnection)new URL(origin+"/api/v1"+path).openConnection();connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(10000);connection.setReadTimeout(10000);connection.setRequestProperty("X-Printer-Token",token);connection.setRequestProperty("Content-Type","application/json");
  try{if(body!=null){connection.setRequestMethod("POST");connection.setDoOutput(true);try(OutputStream out=connection.getOutputStream()){out.write(body.toString().getBytes(StandardCharsets.UTF_8));}}
   int status=connection.getResponseCode();if(status==401||status==403){running=false;throw new IOException("Printer authorization rejected; provision the station key again");}if(status<200||status>=300)throw new IOException("Server returned HTTP "+status);
   ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(InputStream in=connection.getInputStream()){byte[] buffer=new byte[4096];int count;while((count=in.read(buffer))!=-1){if(bytes.size()+count>262144)throw new IOException("Response too large");bytes.write(buffer,0,count);}}
   return new JSONObject(bytes.toString("UTF-8")).get("data");
  }finally{connection.disconnect();}
 }
 private void reportPending() throws Exception {
  String jid=journal.getString("job",null);if(jid==null)return;
  String state=journal.getString("state","UNKNOWN");
  try{api("/printer/jobs/"+jid+"/result",new JSONObject().put("state",state));journal.edit().clear().commit();}
  catch(IOException e){if(e.getMessage()!=null&&e.getMessage().contains("HTTP 409")){journal.edit().clear().commit();status("Print outcome uncertain; ask staff for a copy if needed.");}else throw e;}
 }
 private void runLoop(){try{if(!bound.await(20,TimeUnit.SECONDS))throw new Exception("Printer SDK service unavailable");
  while(running){try{
   reportPending();if(!running)break;
   if(!connected){connected=connect();if(!connected)throw new Exception("Printer connection failed; check permission, address and cable");}
   if(!callback(cb->printer.PrinterIsNormal(cb))){connected=false;throw new Exception("Printer not ready; check paper, cover and power");}
   JSONArray jobs=(JSONArray)api("/printer/jobs",null);
   if(jobs.length()>0){String jid=jobs.getJSONObject(0).getString("id");JSONObject job=(JSONObject)api("/printer/jobs/"+jid+"/claim",new JSONObject());
    // Persist UNKNOWN before touching the printer. A crash must never cause automatic resend.
    if(!journal.edit().putString("job",jid).putString("state","UNKNOWN").commit())throw new Exception("Cannot persist print journal; printing blocked");
    byte[] data;try{data=ReceiptRaster.build(job.getJSONObject("receipt"),width);}catch(Exception e){journal.edit().putString("state","FAILED").commit();reportPending();throw e;}
    if(!running)break;
    boolean submitted=true;long printDeadline=SystemClock.elapsedRealtime()+60000;
    for(int offset=0;offset<data.length;offset+=4096){
     if(!running||SystemClock.elapsedRealtime()>printDeadline){submitted=false;break;}
     byte[] packet=java.util.Arrays.copyOfRange(data,offset,Math.min(data.length,offset+4096));
     if(!callback(cb->printer.Write(packet,cb))){submitted=false;break;}
    }
    journal.edit().putString("state",submitted?"SUBMITTED":"UNKNOWN").commit();reportPending();
    status(submitted?"Receipt submitted; paper delivery is not sensor-confirmed":"Print outcome uncertain. No automatic reprint.");
   }else status("Printer connected. Waiting for paid receipt jobs.");
  }catch(Exception e){status(e instanceof IOException?e.getMessage():"Printer unavailable or job uncertain; check device and server.");}
   if(running)Thread.sleep(2000);
  }
 }catch(Exception e){status("Printer worker stopped; reopen hardware settings.");}
 finally{running=false;token=null;stopSelf();}}
 @Override public void onDestroy(){running=false;executor.shutdownNow();if(registered){try{unbindService(connection);}catch(Exception ignored){}}printer=null;token=null;super.onDestroy();}
}
