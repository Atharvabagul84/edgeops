export const FRONTEND_RELEASE=Object.freeze({version:'0.3.0',id:'edgeops-0.3.0'});

const apiError = (message,status=0,code='API_ERROR') => Object.assign(new Error(message),{status,code});
let activeConfig={mode:'local'};
let readToken=null;

export const validateConfig = (value) => {
  const invalid=()=>apiError('Cloud configuration is invalid. Check cloud-config.json before connecting.',0,'CONFIG_INVALID');
  if (!value || typeof value!=='object' || Array.isArray(value)) throw invalid();
  if (value.mode==='local') return Object.freeze({mode:'local'});
  const {mode,region,userPoolId,clientId,apiBaseUrl}=value;
  if (mode!=='aws' || typeof region!=='string' || !/^[a-z]{2}(?:-[a-z]+)+-\d+$/.test(region)) throw invalid();
  if (typeof userPoolId!=='string' || !userPoolId.startsWith(`${region}_`) || !/^[a-z0-9-]+_[A-Za-z0-9]+$/.test(userPoolId)) throw invalid();
  if (typeof clientId!=='string' || !/^[\w+]{1,128}$/.test(clientId) || typeof apiBaseUrl!=='string') throw invalid();
  let url;
  try { url=new URL(apiBaseUrl); } catch { throw invalid(); }
  const suffix=region.startsWith('cn-') ? 'amazonaws.com.cn' : 'amazonaws.com';
  const domainSuffix=`.execute-api.${region}.${suffix}`;
  if (url.protocol!=='https:' || url.username || url.password || url.port || url.search || url.hash ||
      !url.hostname.endsWith(domainSuffix) || !/^[a-z0-9]+$/.test(url.hostname.slice(0,-domainSuffix.length)) ||
      !/^\/(?:[A-Za-z0-9_$-]+\/?)?$/.test(url.pathname)) throw invalid();
  return Object.freeze({mode,region,userPoolId,clientId,apiBaseUrl:url.href.replace(/\/$/,'')});
};

export const loadConfig = async () => {
  let response;
  try { response=await fetch('/cloud-config.json',{cache:'no-store',credentials:'same-origin',redirect:'error',signal:AbortSignal.timeout(12000)}); }
  catch { throw apiError('Cloud configuration could not be loaded. Reconnect before continuing.',0,'CONFIG_UNAVAILABLE'); }
  if(response.status===404) return {mode:'local'};
  if(!response.ok) throw apiError(`Cloud configuration could not be loaded (${response.status}).`,response.status,'CONFIG_UNAVAILABLE');
  let data;
  try { data=await response.json(); } catch { throw apiError('Cloud configuration must be valid JSON.',0,'CONFIG_INVALID'); }
  return validateConfig(data);
};

export const configureApi = (config,tokenGetter=null) => {
  activeConfig=validateConfig(config);
  readToken=typeof tokenGetter==='function' ? tokenGetter : null;
};

export const request = async (path, body) => {
  if (typeof path!=='string' || !/^\/api\/(state|actions|tick|reset|export|health|telemetry)$/.test(path)) throw apiError('Unsupported API path.',0,'INVALID_API_PATH');
  const config=activeConfig;
  const headers=body===undefined ? {} : {'Content-Type':'application/json'};
  if(config.mode==='aws') {
    const token=await readToken?.();
    if(typeof token!=='string' || !token) throw apiError('Please sign in to connect to your AWS fleet.',401,'AUTH_REQUIRED');
    headers.Authorization=`Bearer ${token}`;
  }
  const response = await fetch(config.mode==='aws' ? config.apiBaseUrl+path : path, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    credentials:config.mode==='aws' ? 'omit' : 'same-origin',
    redirect:'error',
    ...(body === undefined ? {} : {body:JSON.stringify(body)}),
    signal: AbortSignal.timeout(12000),
  });
  if(response.status===401) throw apiError('Your session is no longer authorized. Please sign in again.',401,'AUTH_REQUIRED');
  let data;
  try { data=await response.json(); } catch { throw apiError('The service returned an unreadable response.',response.status,'INVALID_RESPONSE'); }
  if (!response.ok) throw apiError(data.error || data.message || `Request failed (${response.status})`,response.status);
  return data;
};
