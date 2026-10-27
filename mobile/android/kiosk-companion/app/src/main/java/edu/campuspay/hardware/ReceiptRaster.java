package edu.campuspay.hardware;
import android.graphics.*;
import org.json.*;
import java.util.*;
import java.io.ByteArrayOutputStream;

final class ReceiptRaster {
 static byte[] build(JSONObject r,int width) throws Exception {
  if(width!=384&&width!=576)throw new Exception("Unsupported paper width");
  ArrayList<String> lines=new ArrayList<>();
  lines.add("EGS Pillay / CampusPay");lines.add("PAYMENT SUCCESSFUL");lines.add(r.optString("merchant"));lines.add(r.optString("institution"));
  lines.add("Receipt: "+r.optString("receipt_number"));lines.add("Order: "+r.optString("order_reference"));
  JSONArray items=r.getJSONArray("lines");if(items.length()>50)throw new Exception("Receipt too large");
  for(int i=0;i<items.length();i++){JSONObject item=items.getJSONObject(i);lines.add(item.getString("name")+" x "+item.getInt("quantity"));lines.add("Rs. "+item.getLong("line_total_cu"));}
  lines.add("Paid: Rs. "+r.getLong("amount_cu"));lines.add("Balance: Rs. "+r.getLong("balance_after_cu"));
  lines.add(r.optString("paid_at"));lines.add(r.optString("warning"));
  Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setColor(Color.BLACK);paint.setTextSize(width==384?22:26);paint.setTypeface(Typeface.create(Typeface.SANS_SERIF,Typeface.NORMAL));
  ArrayList<String> wrapped=new ArrayList<>();int usable=width-24;
  for(String line:lines){line=line.replaceAll("[\\p{Cntrl}]"," ");if(line.length()>2000)throw new Exception("Receipt field too long");while(!line.isEmpty()){int count=paint.breakText(line,true,usable,null);if(count<1)count=1;wrapped.add(line.substring(0,count));line=line.substring(count);}wrapped.add("");}
  int height=(wrapped.size()+1)*32;if(height>8192)throw new Exception("Receipt exceeds print limit");
  Bitmap bitmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(bitmap);canvas.drawColor(Color.WHITE);int y=28;for(String text:wrapped){canvas.drawText(text,12,y,paint);y+=32;}
  ByteArrayOutputStream out=new ByteArrayOutputStream();out.write(new byte[]{27,64});
  // Standard POS raster bands. No raw receipt text or control sequences reach the printer.
  int rowBytes=width/8;
  for(int top=0;top<height;top+=128){int rows=Math.min(128,height-top);out.write(new byte[]{29,118,48,0,(byte)rowBytes,(byte)(rowBytes>>8),(byte)rows,(byte)(rows>>8)});
   for(int row=0;row<rows;row++)for(int x=0;x<width;x+=8){int bits=0;for(int bit=0;bit<8;bit++){int color=bitmap.getPixel(x+bit,top+row);if((Color.red(color)*30+Color.green(color)*59+Color.blue(color)*11)/100<160)bits|=128>>bit;}out.write(bits);}}
  bitmap.recycle();out.write(new byte[]{10,10,10});return out.toByteArray();
 }
}
