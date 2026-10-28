export const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const number = (value) => Number(value || 0).toLocaleString('en-US');
export const decimal = (value) => Number(value || 0).toFixed(1);
export const time = (value) => value ? new Date(value).toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : 'Not yet';
export const status = (value) => `<span class="status ${['healthy','warning','offline','resolved','open'].includes(value) ? value : ''}"><i></i>${escapeHtml(value || 'unknown')}</span>`;
export const relativeTime = (value, now = new Date()) => {
  if (!value) return 'Awaiting first reading';
  const seconds = Math.max(0, Math.floor((new Date(now) - new Date(value)) / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
};

export const releasePresentation=(frontend,{phase='pending',release}={})=>{
  const base={phase,apiRelease:null,summary:`UI v${frontend.version}`};
  if(phase==='pending') return {...base,state:'pending',summary:`${base.summary} · API pending`,detail:'Waiting for an API response.'};
  if(phase!=='received') return {...base,state:'unavailable',summary:`${base.summary} · API unverified`,detail:'Last request failed. The API release is not currently verified.'};
  const valid=release && typeof release.version==='string' && /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/.test(release.version) &&
    typeof release.id==='string' && /^[A-Za-z0-9._-]{1,80}$/.test(release.id);
  if(!valid) return {...base,state:'unknown',summary:`${base.summary} · API unknown`,detail:'The API response did not include valid release metadata.'};
  const matches=frontend.version===release.version && frontend.id===release.id;
  return {...base,apiRelease:{version:release.version,id:release.id},state:matches?'matched':'mismatch',
    summary:`${base.summary} · API v${release.version}`,
    detail:matches?'Releases match':`Release mismatch · UI ${frontend.id} / API ${release.id}`};
};
