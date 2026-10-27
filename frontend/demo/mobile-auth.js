"use strict";
const MobileAuth = {
  isMobile: () => Boolean(navigator.userAgentData?.mobile) || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1),
  async available() {
    return Boolean(window.isSecureContext && window.PublicKeyCredential && navigator.credentials && await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable());
  },
  decode(s) { return Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')), c=>c.charCodeAt(0)); },
  encode(b) { return b ? btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'') : null; },
  async run(options, register=false) {
    if (!await this.available()) throw Error('Mobile authentication requires HTTPS and a configured device screen lock/passkey. No payment was taken.');
    const publicKey = {...options, challenge:this.decode(options.challenge)};
    if(register) {
      publicKey.user={...options.user,id:this.decode(options.user.id)};
      publicKey.excludeCredentials=(options.excludeCredentials||[]).map(c=>({...c,id:this.decode(c.id)}));
    } else {
      publicKey.allowCredentials=(options.allowCredentials||[]).map(c=>({...c,id:this.decode(c.id)}));
    }
    const c = register ? await navigator.credentials.create({publicKey}) : await navigator.credentials.get({publicKey});
    if(!c || c.authenticatorAttachment !== 'platform') throw Error('Use the mobile device built-in authenticator.');
    const response={clientDataJSON:this.encode(c.response.clientDataJSON)};
    if(register) { response.attestationObject=this.encode(c.response.attestationObject); response.transports=c.response.getTransports?.()||[]; }
    else { response.authenticatorData=this.encode(c.response.authenticatorData); response.signature=this.encode(c.response.signature); response.userHandle=this.encode(c.response.userHandle); }
    return {id:c.id,rawId:this.encode(c.rawId),type:c.type,response,authenticatorAttachment:c.authenticatorAttachment,clientExtensionResults:c.getClientExtensionResults()};
  }
};
