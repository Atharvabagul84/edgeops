import { validateConfig } from './api.js';

const authError=(message,code='AUTH_ERROR',status=400)=>Object.assign(new Error(message),{code,status});
const messages={
  NotAuthorizedException:'The username or password is incorrect, or the temporary password has expired.',
  UserNotFoundException:'The username or password is incorrect.',
  UserNotConfirmedException:'This account is not confirmed. Ask the workspace owner to activate it.',
  PasswordResetRequiredException:'A password reset is required. Ask the workspace owner to reset your account.',
  InvalidPasswordException:'The new password does not meet the user pool password policy.',
  PasswordHistoryPolicyViolationException:'Choose a password you have not used previously.',
  TooManyRequestsException:'Too many sign-in attempts. Wait a moment and try again.',
  LimitExceededException:'The sign-in limit was reached. Wait a moment and try again.',
  InvalidParameterException:'The sign-in details or required attributes are invalid.',
};

// Passwords and Cognito tokens stay in closure memory. Nothing is written to browser storage.
export const createAuthSession=(input,{onChange=()=>{},now=()=>Date.now()}={})=>{
  const config=validateConfig(input);
  if(config.mode!=='aws') throw authError('AWS configuration is required for cloud sign-in.','CONFIG_INVALID');
  const suffix=config.region.startsWith('cn-') ? 'amazonaws.com.cn' : 'amazonaws.com';
  const endpoint=`https://cognito-idp.${config.region}.${suffix}/`;
  let idToken=null,refreshToken=null,expiresAt=null,username='',challenge=null,version=0,refreshing=null;
  let status='signed-out',reason=null;
  const getSession=()=>({status,username,expiresAt,requiredAttributes:[...(challenge?.requiredAttributes || [])],reason});
  const emit=()=>{onChange(getSession());return getSession();};
  const clear=(why='signed-out')=>{
    version++; idToken=null; refreshToken=null; expiresAt=null; username=''; challenge=null; refreshing=null;
    status='signed-out'; reason=why;
    return emit();
  };
  const current=(revision)=>{if(revision!==version) throw authError('Sign-in was cancelled.','AUTH_CANCELLED',409);};
  const call=async(action,payload)=>{
    let response;
    try {
      response=await fetch(endpoint,{method:'POST',credentials:'omit',redirect:'error',
        headers:{'Content-Type':'application/x-amz-json-1.1','X-Amz-Target':`AWSCognitoIdentityProviderService.${action}`},
        body:JSON.stringify(payload),signal:AbortSignal.timeout(15000)});
    } catch { throw authError('Could not connect to AWS sign-in. Check your connection and try again.','AUTH_NETWORK',0); }
    let data;
    try {data=await response.json();} catch {throw authError('AWS sign-in returned an unreadable response.','AUTH_RESPONSE',502);}
    if(!response.ok){
      const code=String(data.__type || data.code || '').split('#').at(-1);
      throw authError(messages[code] || 'AWS could not complete sign-in. Check the account setup and try again.',code || 'AUTH_ERROR',response.status);
    }
    return data;
  };
  const accept=(data,who,revision)=>{
    current(revision);
    if(data.ChallengeName==='NEW_PASSWORD_REQUIRED'){
      let required;
      try {required=JSON.parse(data.ChallengeParameters?.requiredAttributes || '[]');} catch {throw authError('AWS returned invalid required account attributes.','AUTH_RESPONSE',502);}
      if(!Array.isArray(required) || !required.every(value=>typeof value==='string' && /^(?:userAttributes\.)?[A-Za-z0-9_:]+$/.test(value)) || typeof data.Session!=='string' || !data.Session) throw authError('AWS returned an invalid password-change challenge.','AUTH_RESPONSE',502);
      challenge={session:data.Session,username:data.ChallengeParameters?.USER_ID_FOR_SRP || data.ChallengeParameters?.USERNAME || who,requiredAttributes:required.map(value=>value.replace(/^userAttributes\./,''))};
      username=who; status='new-password-required';reason=null;
      return emit();
    }
    if(data.ChallengeName){
      clear('unsupported-challenge');
      throw authError('This account requires an additional sign-in method that this MVP does not support. Ask the workspace owner to check the user pool setup.','AUTH_UNSUPPORTED');
    }
    const result=data.AuthenticationResult;
    if(!result || typeof result.IdToken!=='string' || !result.IdToken || !Number.isFinite(result.ExpiresIn) || result.ExpiresIn<=0 || result.ExpiresIn>86400) throw authError('AWS did not return a valid authenticated session.','AUTH_RESPONSE',502);
    idToken=result.IdToken;
    refreshToken=result.RefreshToken || refreshToken;
    expiresAt=now()+result.ExpiresIn*1000;
    username=who; challenge=null; status='authenticated'; reason=null;
    return emit();
  };
  const signIn=async(who,password)=>{
    if(typeof who!=='string' || !who.trim() || typeof password!=='string' || !password) throw authError('Enter your username and password.','AUTH_INPUT');
    clear();
    const revision=version;
    try {
      const data=await call('InitiateAuth',{AuthFlow:'USER_PASSWORD_AUTH',ClientId:config.clientId,AuthParameters:{USERNAME:who.trim(),PASSWORD:password}});
      return accept(data,who.trim(),revision);
    } catch(error) {if(revision===version) clear();throw error;}
  };
  const completeNewPassword=async(password,attributes={})=>{
    if(!challenge) throw authError('Sign in with your temporary password first.','AUTH_REQUIRED',401);
    if(typeof password!=='string' || !password) throw authError('Enter a new password.','AUTH_INPUT');
    const responses={USERNAME:challenge.username,NEW_PASSWORD:password};
    for(const key of challenge.requiredAttributes){
      const value=attributes[key] ?? attributes[`userAttributes.${key}`];
      if(typeof value!=='string' || !value.trim()) throw authError(`Enter the required ${key.replaceAll('_',' ')} attribute.`,'AUTH_INPUT');
      responses[`userAttributes.${key}`]=value.trim();
    }
    const revision=version;
    const data=await call('RespondToAuthChallenge',{ChallengeName:'NEW_PASSWORD_REQUIRED',ClientId:config.clientId,Session:challenge.session,ChallengeResponses:responses});
    return accept(data,username,revision);
  };
  const getToken=async()=>{
    if(!idToken || status!=='authenticated') throw authError('Please sign in to connect to your AWS fleet.','AUTH_REQUIRED',401);
    if(now()<expiresAt-30000) return idToken;
    if(refreshing) return refreshing;
    if(!refreshToken){clear('expired');throw authError('Your session expired. Please sign in again.','SESSION_EXPIRED',401);}
    const revision=version;
    const who=username;
    refreshing=(async()=>{
      try {
        const data=await call('InitiateAuth',{AuthFlow:'REFRESH_TOKEN_AUTH',ClientId:config.clientId,AuthParameters:{REFRESH_TOKEN:refreshToken}});
        accept(data,who,revision);
        return idToken;
      } catch(error) {
        if(revision!==version) throw error;
        clear('expired');
        throw authError('Your session expired. Please sign in again.','SESSION_EXPIRED',401);
      } finally {if(revision===version) refreshing=null;}
    })();
    return refreshing;
  };
  return Object.freeze({signIn,completeNewPassword,signOut:(why='signed-out')=>clear(why==='expired' ? 'expired' : 'signed-out'),getToken,getSession});
};
