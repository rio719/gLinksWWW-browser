const { contextBridge, ipcRenderer } = require('electron');
let lastUrl = location.href;


window.electronAPI = {
    getCookieValue: (data) => ipcRenderer.invoke('get-cookie-value', data),
    saveCookie: (data) => ipcRenderer.invoke('save-cookie', data)
};

console.log("✅ [지링스] Preload script가 로드되었습니다!");
// 0.5초마다 URL 변화 감시 (유튜브 영상 클릭 감지)
setInterval(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    
    // 영상 페이지(/watch)일 때만 새로고침 실행
    if (location.pathname === '/watch') {
      console.log("지링스 엔진: 영상 감지됨. 강제 리로딩 시작!");
      location.reload(); 
    }
  }
}, 500);
window.addEventListener('DOMContentLoaded', () => {
  const script = document.createElement('script');
  script.textContent = `
    window.alert = (msg) => {
      window.postMessage({ type: 'GLINKS_ALERT', text: msg }, '*');
    };
  `;
  document.head.appendChild(script);
});

window.addEventListener('message', (event) => {
  if (event.data.type === 'GLINKS_ALERT') {
    ipcRenderer.send('site-alert', event.data.text);
  }
});
window.addEventListener('popstate', () => {
    // URL이 바뀔 때(영상 클릭 시) 0.5초 뒤에 비디오를 강제로 깨웁니다.
    setTimeout(() => {
        const video = document.querySelector('video');
        if (video && video.readyState === 0) { // 0은 데이터가 전혀 없다는 뜻
            console.log('유튜브가 뻗어있네요. 강제로 깨웁니다!');
            location.reload(); // 유저 대신 코드가 새로고침을 해버림
        }
    }, 500);
});
// 기존 코드에서
const accounts = await ipcRenderer.invoke('get-accounts');
accounts.forEach((account, index) => {
    // 버튼 클릭 시
    ipcRenderer.invoke('login-with-account', index).then(success => {
        if (success) {
            console.log('자동로그인 성공!');
        }
    });
});