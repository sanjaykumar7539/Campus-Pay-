const roleGrid=document.getElementById('roleGrid'), staffForm=document.getElementById('loginForm');
let selectedRole='';
roleGrid.querySelectorAll('[data-role]').forEach(b=>b.onclick=()=>{selectedRole=b.dataset.role;roleGrid.hidden=true;if(selectedRole==='STUDENT'){location.href='kiosk.html';}else{staffForm.hidden=false;document.getElementById('user').placeholder=selectedRole==='ADMIN'?'admin':'canteen';document.getElementById('user').focus();}});
document.querySelectorAll('.back-role').forEach(b=>b.onclick=()=>{staffForm.hidden=true;roleGrid.hidden=false;});
staffForm.addEventListener('submit',async e=>{e.preventDefault();const go=document.getElementById('go');go.disabled=true;try{const r=await api('/auth/login',{method:'POST',body:{institution_code:'EGS-ENGG',username:document.getElementById('user').value.trim(),password:document.getElementById('pass').value}});if(r.data.role!==selectedRole){throw new Error('This account does not match the selected role.');}sessionStorage.setItem('cp_token',r.data.access_token);sessionStorage.setItem('cp_role',r.data.role);sessionStorage.setItem('cp_user',r.data.username);location.href=r.data.role==='ADMIN'?'admin.html':'merchant.html';}catch(err){banner(document.getElementById('msg'),'err',err.message);go.disabled=false;}});

if(new URLSearchParams(location.search).get('role')==='student')location.replace('kiosk.html');
