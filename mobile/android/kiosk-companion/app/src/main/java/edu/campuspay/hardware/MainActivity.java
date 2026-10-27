package edu.campuspay.hardware;
import android.app.*;
import android.os.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.hardware.usb.*;
import android.bluetooth.BluetoothAdapter;
import android.net.Uri;
import android.text.InputType;
import android.view.WindowManager;
import android.widget.*;
import android.Manifest;
import java.net.URI;
import java.util.*;

public class MainActivity extends Activity {
 private EditText origin,token,address,port;
 private Spinner transport,width;
 private TextView status;
 private static final String USB_ACTION="edu.campuspay.hardware.USB_PERMISSION";
 private final BroadcastReceiver usbReceiver=new BroadcastReceiver(){ public void onReceive(Context c,Intent i){
   if(USB_ACTION.equals(i.getAction()))status.setText(i.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED,false)?"USB permission granted. Start service.":"USB permission denied; printing blocked.");
 }};
 @Override public void onCreate(Bundle b){super.onCreate(b);
  getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
  LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(24,24,24,24);
  ScrollView scroll=new ScrollView(this);scroll.addView(layout);setContentView(scroll);
  TextView title=new TextView(this);title.setText("CampusPay Android Hardware");title.setTextSize(24);layout.addView(title);
  origin=field(layout,"HTTPS server origin (no path)","https://pay.example.edu");
  token=field(layout,"Station printer key (Admin > Canteens & stations)","");token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
  transport=choice(layout,new String[]{"USB","Bluetooth","LAN"});
  address=field(layout,"USB device path / paired Bluetooth MAC / printer IP","");
  port=field(layout,"LAN port","9100");port.setInputType(InputType.TYPE_CLASS_NUMBER);
  width=choice(layout,new String[]{"58 mm","80 mm"});
  button(layout,"Choose USB printer / grant permission",()->chooseUsb());
  button(layout,"Show paired Bluetooth printers",()->chooseBluetooth());
  button(layout,"Start printer service",()->startWorker());
  button(layout,"Stop printer service",()->{stopService(new Intent(this,PrinterWorker.class));status.setText("Printer service stopped.");});
  button(layout,"Open kiosk website",()->{try{validateOrigin();startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(origin.getText()+"/kiosk.html")));}catch(Exception e){status.setText(e.getMessage());}});
  button(layout,"Morpho RD diagnostics",()->morphoStatus());
  status=new TextView(this);status.setText("Printer service not started. Keys are kept in memory only; enter again after restart. Morpho student matching requires the vendor MSO SDK.");layout.addView(status);
  IntentFilter f=new IntentFilter(USB_ACTION);if(Build.VERSION.SDK_INT>=33)registerReceiver(usbReceiver,f,Context.RECEIVER_NOT_EXPORTED);else registerReceiver(usbReceiver,f);
 }
 private EditText field(LinearLayout l,String label,String value){TextView t=new TextView(this);t.setText(label);l.addView(t);EditText e=new EditText(this);e.setText(value);e.setSingleLine(true);l.addView(e);return e;}
 private Spinner choice(LinearLayout l,String[] values){Spinner s=new Spinner(this);s.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,values));l.addView(s);return s;}
 private void button(LinearLayout l,String name,Runnable fn){Button b=new Button(this);b.setText(name);b.setOnClickListener(v->fn.run());l.addView(b);}
 private void validateOrigin() throws Exception {URI u=new URI(origin.getText().toString().trim());if(!"https".equals(u.getScheme())||u.getHost()==null||u.getRawUserInfo()!=null||u.getQuery()!=null||u.getFragment()!=null||(u.getPath()!=null&&!u.getPath().isEmpty()))throw new Exception("Enter a valid HTTPS origin without slash/path or credentials.");}
 private void chooseUsb(){UsbManager manager=(UsbManager)getSystemService(USB_SERVICE);ArrayList<UsbDevice> devices=new ArrayList<>(manager.getDeviceList().values());if(devices.isEmpty()){status.setText("No USB devices. Check OTG and cable.");return;}
  String[] labels=new String[devices.size()];for(int n=0;n<devices.size();n++){UsbDevice d=devices.get(n);labels[n]=d.getDeviceName()+" VID="+d.getVendorId()+" PID="+d.getProductId();}
  new AlertDialog.Builder(this).setTitle("Select printer, not fingerprint reader").setItems(labels,(dialog,n)->{UsbDevice d=devices.get(n);address.setText(d.getDeviceName());transport.setSelection(0);manager.requestPermission(d,PendingIntent.getBroadcast(this,0,new Intent(USB_ACTION).setPackage(getPackageName()),PendingIntent.FLAG_IMMUTABLE));}).show();
 }
 private void chooseBluetooth(){if(Build.VERSION.SDK_INT>=31&&checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT},12);status.setText("Grant Nearby Devices, then select again.");return;}
  BluetoothAdapter adapter=BluetoothAdapter.getDefaultAdapter();if(adapter==null||!adapter.isEnabled()){status.setText("Enable Bluetooth and pair the printer in Android settings first.");return;}
  ArrayList<android.bluetooth.BluetoothDevice> devices=new ArrayList<>(adapter.getBondedDevices());String[] names=new String[devices.size()];for(int n=0;n<names.length;n++)names[n]=devices.get(n).getName()+" "+devices.get(n).getAddress();
  new AlertDialog.Builder(this).setTitle("Paired printers").setItems(names,(dialog,n)->{transport.setSelection(1);address.setText(devices.get(n).getAddress());}).show();
 }
 private void startWorker(){try{validateOrigin();if(token.getText().length()<32)throw new Exception("Enter the printer key provisioned for this station.");
  if(address.getText().toString().trim().isEmpty())throw new Exception("Select or enter the printer address.");
  String mode=transport.getSelectedItem().toString();int networkPort=Integer.parseInt(port.getText().toString());if(networkPort<1||networkPort>65535)throw new Exception("Invalid printer port.");
  if(mode.equals("USB")){UsbManager m=(UsbManager)getSystemService(USB_SERVICE);UsbDevice d=m.getDeviceList().get(address.getText().toString().trim());if(d==null||!m.hasPermission(d))throw new Exception("Select the USB printer and grant permission first.");}
  if(mode.equals("Bluetooth")&&Build.VERSION.SDK_INT>=31&&checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED)throw new Exception("Grant Nearby Devices permission first.");
  if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},13);
  Intent i=new Intent(this,PrinterWorker.class).putExtra("origin",origin.getText().toString().trim()).putExtra("token",token.getText().toString()).putExtra("transport",mode).putExtra("address",address.getText().toString().trim()).putExtra("port",networkPort).putExtra("width",width.getSelectedItemPosition()==0?384:576);
  startForegroundService(i);token.setText("");status.setText("Printer worker starting. See its notification for connection status. Enable Thermal receipt mode in kiosk activation.");
 }catch(Exception e){status.setText(e.getMessage());}}
 private void morphoStatus(){boolean installed;try{getPackageManager().getPackageInfo("com.scl.rdservice",0);installed=true;}catch(PackageManager.NameNotFoundException e){installed=false;}
  UsbManager m=(UsbManager)getSystemService(USB_SERVICE);StringBuilder info=new StringBuilder("Morpho RD app: "+(installed?"installed":"not found")+"\nUSB devices: "+m.getDeviceList().size()+"\n");
  for(UsbDevice d:m.getDeviceList().values())info.append("VID=").append(d.getVendorId()).append(" PID=").append(d.getProductId()).append("\n");
  info.append("App/device presence is not an enrolled student match. MSO E2 matching SDK adapter is still required. No biometric capture or payment is performed here.");
  new AlertDialog.Builder(this).setTitle("Morpho E2 integration status").setMessage(info).setPositiveButton("OK",null).show();
 }
 @Override public void onDestroy(){try{unregisterReceiver(usbReceiver);}catch(Exception ignored){}super.onDestroy();}
}
