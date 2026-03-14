const { app,session, autoUpdater,globalShortcut, clipboard, BrowserView, BrowserWindow, ipcMain, powerSaveBlocker, dialog,shell } = require('electron');
const path = require('path');
const fs = require('fs');
app.disableHardwareAcceleration();



// 2. 백그라운드 작업 보장 (다중 복붙 로직이 잠들지 않게 함)
//  스위치들이 없으면 앱이 최소화될 때 클립보드 저장 로직이 멈출 수 있습니다.
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');



// 3. IPC 통신 강화 (복사/붙여넣기 데이터가 많을 때 끊김 방지)
app.commandLine.appendSwitch('disable-ipc-flooding-protection');







// 4. 자동 재생 강제 (비디오 앱 필수)

app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.requestSingleInstanceLock();

// 5. 백그라운드 throttling 방지 (비디오 연속 재생용)

app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');

const isPrimaryInstance = app.requestSingleInstanceLock();
if (!isPrimaryInstance) {
  app.quit();
}
let win;
let views = []; 
let currentTabIndex = 0;
let multiClipboard = {};
let tabIcons = []; // 각 탭의 아이콘을 저장하는 배열
const storagePath = path.join(app.getPath('userData'), 'multi-clipboard.json');


// 클립보드 데이터 불러오기
try {
    if (fs.existsSync(storagePath)) {
        multiClipboard = JSON.parse(fs.readFileSync(storagePath, 'utf8'));
    }
} catch (e) { multiClipboard = {}; }
// [수정] 어디서든 호출 가능한 전역 UI 갱신 함수
function refreshUI() {
    if (!win || win.isDestroyed()) return;
    const tabList = views.map((v, i) => ({
        title: v.webContents.getTitle() || "새 탭",
        url: v.webContents.getURL(),
        icon: tabIcons[i] || 'default-icon.png'
    }));
    win.webContents.send('render-tabs', { tabList, activeIndex: currentTabIndex });
}
function createTabView(index) {
    const v = new BrowserView({
        webPreferences: { 
                    nodeIntegration: true, 
            contextIsolation: false,
            // [추가] 팝업 차단 및 보안 설정
            nativeWindowOpen: false ,
            preload: path.join(__dirname, 'preload.js'), 
            // [추가] 하드웨어 가속이 안 먹힐 때를 대비한 미디어 기능 강제 활성화
    webSecurity: true, 
    experimentalFeatures: true, // 크롬 최신 실험 기능을 활성화해서 MSE 코덱 지원 강화
    backgroundThrottling: false // 탭이 가려져도 로딩이 끊기지 않게 함
        }
    });
    // ... 이하 동일
    // 하단에 추가: 모든 웹뷰 세션에서 오디오/비디오 권한을 명시적으로 허용
session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
  if (permission === 'media') return true;
  return true;
});
// 일반적인 브라우저 호환성을 위해 Chrome 정보 뒤에 gLinks 이름을 붙이는 것이 좋습니다.
    v.webContents.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 gLinksWWW/1.2.6 (Chromium)/");
    v.webContents.loadFile('home.html');
// 초기 아이콘 설정 (이미 값이 있다면 덮어쓰지 않음)
    if (!tabIcons[index]) {
        tabIcons[index] = 'default-icon.png';
    }
    // [수정] 새 창이 뜨는 대신 현재 탭에서 링크 열기
    v.webContents.setWindowOpenHandler(({ url }) => {
        v.webContents.loadURL(url);
        return { action: 'deny' }; // 새 창 생성을 거부하고 현재 뷰에서 로드
    });

    // [수정] 로딩 상태 관리 (해당 탭에서만 로딩 문구가 뜨도록)
    v.webContents.on('did-start-loading', () => {
        // 현재 선택된 탭일 때만 UI에 로딩 신호를 보냄
        if (views[currentTabIndex] === v) {
            win.webContents.send('tab-loading-start', index);
        }
    });

    v.webContents.on('did-stop-loading', () => {
        win.webContents.send('tab-loading-stop', index);
    });
// [추가] 1. 실제 페이지 이동이 발생했을 때 (새로운 URL로 이동)
    v.webContents.on('did-navigate', (event, url) => {
        if (views[currentTabIndex] === v) {
            win.webContents.send('update-url', url);
        }
    });
v.webContents.on('will-navigate', (event, url) => {
    // 1. 유튜브 링크인지 확인
    if (url.includes('youtube.com') || url.includes('youtu.be/')) {
        
        // 2. 현재 페이지가 이미 유튜브라면? (유튜브 내부에서 영상 클릭 중)
        const currentURL = v.webContents.getURL();
        if (currentURL.includes('youtube.com/watch')) {
            return; // 그냥 내부에서 재생하게 둡니다 (방해 금지)
        }

        // 3. 유튜브 외부에서 유튜브로 '진입'하려는 순간이라면?
        event.preventDefault(); // 브라우저 내부 로딩 차단!
        const { shell } = require('electron');
        shell.openExternal(url); // 외부 앱으로 던지기
        
        console.log('Intercepted YouTube navigation! Sending to external app...');
    }
});
    // [추가] 2. 페이지 내 섹션 이동 시 (예: #hash 이동이나 SPA 방식 이동)
    v.webContents.on('did-navigate-in-page', (event, url) => {
        if (views[currentTabIndex] === v) {
            win.webContents.send('update-url', url);
        }
    });

    // [추가] 3. 탭을 클릭해서 바꿨을 때도 해당 탭의 URL로 주소창 갱신
    v.webContents.on('did-finish-load', () => {
        refreshUI();
        if (views[currentTabIndex] === v) {
            win.webContents.send('update-url', v.webContents.getURL());
        }
    });
// [핵심] 웹사이트에서 아이콘을 가져왔을 때 호출됨
    v.webContents.on('page-favicon-updated', (event, favicons) => {
        if (favicons && favicons.length > 0) {
            tabIcons[index] = favicons[0]; // 가장 해상도 좋은 첫 번째 아이콘 저장
            refreshUI(); // UI에 즉시 반영
        }
    });

    // 제목이 바뀔 때도 리프레시
    v.webContents.on('page-title-updated', refreshUI);
    return v;
}

// 2. 탭 전환 및 화면 크기 조정
function selectTab(index) {
    if (views[index]) {
        currentTabIndex = index;
        win.setBrowserView(views[index]);
        updateViewBounds();
        
        // UI 상태 업데이트
        const tabList = views.map(view => ({ title: view.webContents.getTitle() || "새 탭" }));
        win.webContents.send('render-tabs', { tabList, activeIndex: currentTabIndex });
        win.webContents.send('update-url', views[index].webContents.getURL());
    }
}
// main.js의 중복된 updateViewBounds를 모두 지우고 이 하나로 통합하세요.
function updateViewBounds() {
    if (!win || !views[currentTabIndex]) return;

    // getContentBounds는 제목 표시줄을 제외한 '실제 안쪽 크기'를 가져옵니다.
    const b = win.getContentBounds(); 
    
    const topBarHeight = 78;    // 상단 탭+주소창 높이
    const bottomMargin = 2;    // [핵심] 작업 표시줄에 가리지 않게 줄 하단 여백

    views[currentTabIndex].setBounds({ 
        x: 0, 
        y: topBarHeight, 
        width: b.width, 
        height: b.height - topBarHeight - bottomMargin // 전체에서 상단과 하단을 모두 뺌!
    });
}

let powerSaveId;
app.whenReady().then(() => {
    win = new BrowserWindow({
       width: 1200,
    height: 1000,
    minWidth: 800,  // 최소 너비 제한
    minHeight: 600, // 최소 높이 제한
    resizable: true, // 사용자가 창 크기를 조절할 수 있게 허용
        webPreferences: { 
       
       nodeIntegration: true, 
    contextIsolation: false, 

    // 2. [핵심] 유튜브가 '노드 흔적'을 못 찾게 차단막 설치
    // preload에서 유튜브가 전역 변수를 검사할 때 노드 관련 키워드를 숨겨야 합니다.
    preload: path.join(__dirname, 'preload.js'), 

    // 3. 나머지는 그대로 유지
    partition: 'persist:user-session',
    webSecurity: true,

 
           
         }
    });

    // [해결] 리스너 제한 해제
    win.setMaxListeners(0); 
    
    win.loadFile('index.html');
    views.push(createTabView(0));
    
    win.webContents.once('did-finish-load', () => selectTab(0));
    win.on('resize', updateViewBounds);
powerSaveId = powerSaveBlocker.start('prevent-display-sleep');
  console.log('Power save blocker started:', powerSaveId);
    // --- 기존 멀티 클립보드 단축키 로직 ---
    // 등록할 키 배열 (0-9 숫자 + F1-F8 키)
const keys = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8'];

keys.forEach((key) => {
    // 1. 복사 등록 (Ctrl/Cmd + Shift + Key)
    globalShortcut.register(`CommandOrControl+Shift+${key}`, () => {
        if (views[currentTabIndex]) {
            views[currentTabIndex].webContents.copy();
            setTimeout(() => {
                // key가 'F1'일 경우 index 관리를 위해 multiClipboard[key] 형태로 저장 추천
                multiClipboard[key] = clipboard.readText();
                fs.writeFileSync(storagePath, JSON.stringify(multiClipboard));
            }, 100);
        }
    });
    globalShortcut.register(`Alt+Shift+${key}`, () => {
        if (views[currentTabIndex]) {
            views[currentTabIndex].webContents.cut();
            setTimeout(() => {
                // key가 'F1'일 경우 index 관리를 위해 multiClipboard[key] 형태로 저장 추천
                multiClipboard[key] = clipboard.readText();
                fs.writeFileSync(storagePath, JSON.stringify(multiClipboard));
            }, 100);
        }
    });
    // 2. 붙여넣기 등록 (Ctrl/Cmd + Alt + Key)
    globalShortcut.register(`CommandOrControl+Alt+${key}`, () => {
        if (multiClipboard[key] && views[currentTabIndex]) {
            clipboard.writeText(multiClipboard[key]);
            views[currentTabIndex].webContents.paste();
        }
    });
});
// 2. [다운로드] 세션 리스너 (딱 한 번만 등록)
    session.defaultSession.on('will-download', (event, item, webContents) => {
        // 경로 선택 창 강제 호출 (이게 있어야 창이 뜹니다)
        const savePath = dialog.showSaveDialogSync(win, {
            defaultPath: item.getFilename()
        });

        if (savePath) {
            item.setSavePath(savePath);
        } else {
            event.preventDefault(); // 취소 시 중단
            return;
        }

        item.on('updated', (event, state) => {
            if (state === 'progressing') {
                win.setProgressBar(item.getReceivedBytes() / item.getTotalBytes());
            }
        });

        item.once('done', (event, state) => {
            win.setProgressBar(-1);
            if (state === 'completed') {
                dialog.showMessageBox(win, { title: 'Completed', message: 'Download completed successfully!' });
            }
        });
    });

    // 2. [핵심] 모든 탭의 알러트/프롬프트 가로채기
    // app.whenReady 안에 이 '감시자'를 심어두는 겁니다.
    // app.whenReady() 내부 어딘가에 딱 한 번만 작성
app.on('web-contents-created', (event, contents) => {
    
    // 이 contents가 바로 새로 생성되는 각 탭(View)들입니다.
    // 여기서 이벤트를 걸어주면 모든 탭에 "세션처럼" 일괄 적용되는 효과가 나요!

    // 1. Alert (알림창)
    contents.on('window-alert', (e, message) => {
        e.preventDefault();
        dialog.showMessageBoxSync(win, { message: String(message), buttons: ['확인'] });
    });

    // 2. Confirm (확인창)
    contents.on('window-confirm', (e, message) => {
        e.preventDefault();
        const result = dialog.showMessageBoxSync(win, {
            type: 'question',
            message: String(message),
            buttons: ['Ok', 'Cancel']
        });
        e.returnValue = (result === 0);
    });

    // 3. Prompt (입력창)
    contents.on('window-prompt', (e, message, defaultValue) => {
        e.preventDefault();
        const result = dialog.showMessageBoxSync(win, {
            type: 'question',
            message: `${message}\n\n(Standard prompt is limited)`,
            buttons: ['Ok', 'Cancel']
        });
        e.returnValue = (result === 0 ? defaultValue : null);
    });
});

    // 3. 다운로드 로직 (session.defaultSession.on...)
    // 4. 단축키 등록 (for문 루프...)
    // ... 나머지 코드
});


// --- IPC 통신 핸들러 ---
// main.js 파일 하단에 추가
ipcMain.on('request-clipboard-data', (event) => {
    // 현재 메모리에 있는 18개 슬롯 데이터를 화면으로 전송
    event.reply('clipboard-data-updated', multiClipboard);
});

ipcMain.on('delete-slot', (event, slotKey) => {
    // 특정 슬롯 삭제
    multiClipboard[slotKey] = ""; 
    fs.writeFileSync(storagePath, JSON.stringify(multiClipboard));
    // 삭제 후 업데이트된 데이터 다시 전송
    event.reply('clipboard-data-updated', multiClipboard);
});
// main.js의 ipcMain.on('request-new-tab', ...) 부분을 수정하세요.
ipcMain.on('request-new-tab', () => {
    // 탭 개수가 8개 이상이면 실행하지 않음
    if (views.length >= 8) {
        win.webContents.send('show-alert', "탭은 최대 8개까지만 열 수 있습니다.");
        return;
    } 

    const newIdx = views.length;
    views.push(createTabView(newIdx));
    selectTab(newIdx);
    
});

ipcMain.on('switch-tab', (e, index) => selectTab(index));

ipcMain.on('load-url', (event, data) => {
    // 1. 데이터 추출 (객체 형태 {url, engine} 또는 문자열 대응)
    let inputUrl = (typeof data === 'string') ? data : (data.url || "");
    let engine = data.engine || "bing"; // 기본값은 빙으로 설정

    if (!inputUrl) return;

    let finalUrl = inputUrl;

    // 2. HTTP로 시작하지 않으면 검색 엔진 적용
    if (!inputUrl.startsWith('http://') && !inputUrl.startsWith('https://')) {
       const query = encodeURIComponent(inputUrl);
        
        switch (engine) {
            case 'google':
                finalUrl = `https://www.google.com/search?q=${query}`;
                break;
            case 'brave':
                finalUrl = `https://search.brave.com/search?q=${query}`;
                break;
            case 'startpage':
                finalUrl = `https://www.startpage.com/do/dsearch?query=${query}`;
                break;
            case 'yandex':
                finalUrl = `https://yandex.com/search/?text=${query}`;
                break;
            case 'perplexity':
                finalUrl = `https://www.perplexity.ai/search?q=${query}`;
                break;
            case 'yahoo':
                finalUrl = `https://search.yahoo.com/search?p=${query}`;
                break;
            case 'bing': // 기본값 빙(Bing)
                finalUrl = `https://www.bing.com/search?q=${query}`;
        }
    }
    if (finalUrl.includes('https://www.youtube.com') || finalUrl.includes('https://youtu.be')|| finalUrl.includes('https://youtube.com')) {
        
        shell.openExternal(finalUrl); // 외부 브라우저나 앱으로 실행
        
        // 브라우저 내부에서는 로딩 중단 혹은 '홈'이나 '안내 페이지'로 보냄
        if (views[currentTabIndex]) {
            win.webContents.send('tab-loading-stop'); // 로딩 UI 멈춤
            // 팁: 내부 뷰에는 "유튜브는 외부 앱에서 실행 중입니다" 같은 안내를 띄워도 좋습니다.
        }
        return; // 여기서 함수 종료 (내부 로드를 하지 않음)
    }
    // 3. 현재 탭에 로드
    if (views[currentTabIndex]) {
        win.webContents.send('tab-loading-start'); // 로딩 UI 시작
        views[currentTabIndex].webContents.loadURL(finalUrl);
        win.setBrowserView(views[currentTabIndex]);
        updateViewBounds();
    }
});
// 3. 탭 삭제 로직 (아이콘 동기화 포함)
ipcMain.on('delete-tab', (event, index) => {
    if (views.length <= 1) return;

    const targetView = views[index];
    if (targetView) {
        win.removeBrowserView(targetView);
        targetView.webContents.destroy();
        
        views.splice(index, 1);
        tabIcons.splice(index, 1); // [중요] 아이콘 배열도 함께 정리
        
        if (currentTabIndex >= index) {
            currentTabIndex = Math.max(0, currentTabIndex - 1);
        }
        selectTab(currentTabIndex);
    }
});

ipcMain.on('go-back', () => { if (views[currentTabIndex].webContents.canGoBack()) views[currentTabIndex].webContents.goBack(); });

ipcMain.on('go-forward', () => { if (views[currentTabIndex].webContents.canGoForward()) views[currentTabIndex].webContents.goForward(); });

ipcMain.on('reload', () => { views[currentTabIndex].webContents.reload(); });

ipcMain.on('go-home', () => { views[currentTabIndex].webContents.loadFile('home.html'); });
ipcMain.on('open-clipboard-manager', () => { views[currentTabIndex].webContents.loadFile('clipboard.html'); });


// 공통 Alert/Prompt 처리

ipcMain.on('site-alert', (event, message) => {
    dialog.showMessageBoxSync(win, {
        type: 'none',
        title: 'gLinksWWW Message',
        message: String(message),
        buttons: ['OK'],
        noLink: true
    });
});

// 2. Prompt 가로채기 (OS 기본 입력창이 없으므로 confirm 형식을 빌리거나 창을 띄워야 함)
ipcMain.on('site-prompt', (event, message, defaultValue) => {
    // OS 표준은 아니지만, 가장 근접한 시스템 다이얼로그
    const result = dialog.showMessageBoxSync(win, {
        type: 'question',
        title: 'gLinksWWW Input',
        message: `${message}\n\n(Note: OS standard prompt is limited. Use OK to proceed)`,
        buttons: ['OK', 'Cancel'],
        defaultId: 0,
        cancelId: 1
    });

    // 응답을 다시 웹뷰로 돌려줘야 사이트가 멈추지 않습니다.
    event.reply('prompt-response', result === 0 ? defaultValue : null);
});



// 크기 조절 함수









// 불러오기

try {

  multiClipboard = JSON.parse(fs.readFileSync(storagePath, 'utf8'));

} catch (e) {

  multiClipboard = {};

}



// 저장하기 (복사할 때마다 호출)

function saveClipboard() {

  fs.writeFileSync(storagePath, JSON.stringify(multiClipboard));

}

// 앱 종료 시 단축키 해제

app.on('will-quit', () => {

  globalShortcut.unregisterAll();

});

// 창 크기가 바뀔 때 대응

app.on('browser-window-created', (e, window) => {

    window.on('resize', () => { updateViewBounds(); });

});
// main.js 하단에 추가
ipcMain.on('clear-site-cookies', async (event, domain) => {
    try {
        // 특정 도메인에 해당하는 쿠키들만 가져오기
        const cookies = await session.defaultSession.cookies.get({ domain: domain });
        
        for (let cookie of cookies) {
            // 쿠키 삭제를 위한 URL 생성 (보안 여부에 따라 다름)
            let protocol = cookie.secure ? 'https://' : 'http://';
            let host = cookie.domain.startsWith('.') ? cookie.domain.substring(1) : cookie.domain;
            let url = protocol + host + cookie.path;
            
            await session.defaultSession.cookies.remove(url, cookie.name);
        }
        
        console.log(`[지링스 보안] ${domain} 관련 쿠키가 모두 파괴되었습니다.`);
        event.reply('cookies-cleared-success', domain);
    } catch (error) {
        console.error('쿠키 삭제 실패:', error);
    }
});

ipcMain.on('open-cookie-manager', () => { views[currentTabIndex].webContents.loadFile('cookie.html'); });
ipcMain.on('open-account-manager', () => { views[currentTabIndex].webContents.loadFile('account.html'); });
// main.js


// 1. 모든 쿠키 가져오기 핸들러
ipcMain.handle('get-cookies', async () => {
    try {
        const cookies = await session.defaultSession.cookies.get({});
        // 현재 활성화된 탭의 URL에서 호스트네임 추출
        let currentHost = "";
        if (views[currentTabIndex]) {
            const url = new URL(views[currentTabIndex].webContents.getURL());
            currentHost = url.hostname;
        }
        
        return { cookies, currentHost }; // 👈 두 정보를 같이 보냄!
    } catch (error) {
        return { cookies: [], currentHost: "" };
    }
});

// 2. 특정 도메인 쿠키 삭제 핸들러
ipcMain.handle('delete-cookies', async (event, domain) => {
    try {
        const cookies = await session.defaultSession.cookies.get({ domain });
        for (let cookie of cookies) {
            let protocol = cookie.secure ? 'https://' : 'http://';
            let host = cookie.domain.startsWith('.') ? cookie.domain.substring(1) : cookie.domain;
            let url = protocol + host + cookie.path;
            await session.defaultSession.cookies.remove(url, cookie.name);
        }
        return true;
    } catch (error) {
        console.error('쿠키 삭제 실패:', error);
        return false;
    }
});
// main.js에 추가
ipcMain.handle('get-current-url', () => {
    if (views[currentTabIndex]) {
        return views[currentTabIndex].webContents.getURL();
    }
    return "";
});
// main.js의 ipcMain.handle 부분에 추가
ipcMain.handle('clear-all-cookies', async () => {
    try {
        const cookies = await session.defaultSession.cookies.get({});
        for (let cookie of cookies) {
            let protocol = cookie.secure ? 'https://' : 'http://';
            let host = cookie.domain.startsWith('.') ? cookie.domain.substring(1) : cookie.domain;
            let url = protocol + host + cookie.path;
            await session.defaultSession.cookies.remove(url, cookie.name);
        }
        return true;
    } catch (error) {
        console.error('전체 소거 실패:', error);
        return false;
    }
});
//구글 계정 연동 기능
const accountsPath = path.join(app.getPath('userData'), 'accounts.json');
let localAccounts = [];

// 로컬 계정 파일 로드 (에러 로그 강화)
try {
    if (fs.existsSync(accountsPath)) {
        localAccounts = JSON.parse(fs.readFileSync(accountsPath, 'utf8'));
        console.log('계정 로드 성공:', localAccounts.length, '개');
    } else {
        console.log('accounts.json 파일 없음, 새로 생성');
    }
} catch (e) {
    console.error('계정 로드 실패:', e);
    localAccounts = [];
}

// 1. 계정 목록 가져오기
ipcMain.handle('get-accounts', () => localAccounts);

// 2. 계정 추가 처리 (완전 비동기 버전)
async function saveNewAccount(userData, authWindow = null) {
    try {
        if (localAccounts.length < 10) {
            let cookies = [];
            
            if (authWindow && authWindow.webContents && !authWindow.isDestroyed()) {
                try {
                    cookies = await authWindow.webContents.session.cookies.get({
                        urls: ['.google.com', 'accounts.google.com']
                    });
                    console.log(`📋 쿠키 가져옴: ${cookies.length}개`);
                } catch (cookieError) {
                    console.warn('쿠키 가져오기 실패:', cookieError.message);
                }
            }
            
            // 🔥 여기에 핵심 쿠키 필터링 추가!
            const essentialCookies = cookies.filter(cookie => 
                ['SID', 'HSID', 'SSID', 'APISID', 'SAPISID', 'NID', '1P_JAR'].includes(cookie.name)
            );
            
            // 쿠키 직렬화 (핵심 쿠키만!)
            userData.cookies = essentialCookies.map(cookie => ({
                name: cookie.name,
                value: cookie.value,
                domain: cookie.domain,
                path: cookie.path,
                secure: cookie.secure || false,
                httpOnly: cookie.httpOnly || false,
                expirationDate: cookie.expirationDate || Math.floor(Date.now() / 1000) + 86400
            }));
            
            localAccounts.push(userData);
            fs.writeFileSync(accountsPath, JSON.stringify(localAccounts, null, 2), 'utf8');
            
            console.log(`✅ ${userData.email} 핵심 쿠키 저장 (${userData.cookies.length}개)`);
            
            const mainWindow = BrowserWindow.getAllWindows()[0];
            if (mainWindow) {
                mainWindow.webContents.send('accounts-updated');
            }
            return true;
        }
        return false;
    } catch (e) {
        console.error('저장 실패:', e);
        return false;
    }
}

// 3. 계정 삭제 처리
ipcMain.handle('delete-account', (event, index) => {
    try {
        localAccounts.splice(index, 1);
        fs.writeFileSync(accountsPath, JSON.stringify(localAccounts, null, 2), 'utf8');
        console.log('계정 삭제 성공');
        return true;
    } catch (e) {
        console.error('계정 삭제 실패:', e);
        return false;
    }
});
// 계정별 세션 매핑 (메모리 저장)
const accountSessions = new Map(); // email -> partition 이름

// 저장된 계정으로 프로필 세션 불러오기
ipcMain.handle('load-account-session', async (event, email) => {
    const partitionName = `persist:google-${email.replace(/[@.]/g, '_')}`;
    
    // 계정 데이터 로드
    const account = localAccounts.find(acc => acc.email === email);
    if (!account) return { success: false, error: '계정 없음' };
    
    console.log(`📂 ${email} 프로필 세션 로드`);
    
    // 새 탭에서 이 세션 사용하도록 설정
    const mainWindow = BrowserWindow.getAllWindows()[0];
    if (mainWindow) {
        mainWindow.webContents.send('session-ready', { email, partition: partitionName });
    }
    
    return { success: true, partition: partitionName };
});

ipcMain.on('start-oauth', async (event, provider) => {
    if (localAccounts.length >= 10) {
        console.warn('최대 계정 수 도달');
        return;
    }

    const mainSession = session.defaultSession; // 🔥 최상단에 메인 세션 정의!

    // 핵심 수정: partition으로 세션 격리 (Google 쿠키 캐싱 방지)
    const authSession = session.fromPartition('persist:auth-temp');
    authSession.clearStorageData();

    let authWin = new BrowserWindow({
        width: 500,
        height: 700,
        show: false,
        autoHideMenuBar: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            partition: 'persist:auth-temp'
        }
    });

    authWin.show();

    const supabaseUrl = "https://uplcvngycheslyskgtes.supabase.co";
    const queryParams = { prompt: 'select_account' };
    const encodedParams = encodeURIComponent(JSON.stringify(queryParams));
    const authUrl = `${supabaseUrl}/auth/v1/authorize?provider=${provider}&redirect_to=http://localhost:3000&queryParams=${encodedParams}`;

    console.log('OAuth 시작 URL:', authUrl);

    const handleResponse = async (url) => {
        console.log('리다이렉트 감지:', url);
        if (url.includes('access_token')) {
            try {
                const urlObj = new URL(url.includes('#') ? url.replace('#', '?') : url);
                const accessToken = urlObj.searchParams.get('access_token');
                const providerToken = urlObj.searchParams.get('provider_token');
                
                if (accessToken && providerToken) {
                    console.log('✅ 토큰 획득:', providerToken.substring(0, 20) + '...');
                    
                    // 1. 사용자 정보 추출
                    const googleResponse = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
                        headers: { Authorization: `Bearer ${providerToken}` }
                    });
                    
                    let userData = { email: 'unknown' };
                    if (googleResponse.ok) {
                        userData = await googleResponse.json();
                        console.log('✅ Google UserInfo 성공:', userData.email);
                    } else {
                        const decodedPayload = JSON.parse(atob(accessToken.split('.')[1]));
                        userData.email = decodedPayload.email || 'unknown';
                        userData.name = decodedPayload.user_metadata?.full_name || decodedPayload.user_metadata?.name;
                    }
                    
                    // handleResponse 내부
if (userData.email && userData.email !== 'unknown') {
    const newAcc = {
        provider: provider,
        email: userData.email,
        name: userData.name || userData.given_name || 'N/A',
        picture: userData.picture || '',
        addedAt: new Date().toISOString()
    };
    
    // 🔥 async/await로 호출!
    const saved = await saveNewAccount(newAcc, authWin);
    
    if (saved) {
        console.log('🎉 완전 저장 완료:', newAcc.email);
        const mainWindow = BrowserWindow.getAllWindows()[0];
        if (mainWindow) {
            mainWindow.webContents.send('oauth-success', newAcc);
        }
    }
}
                }
            } catch (e) {
                console.error('❌ OAuth 처리 에러:', e.message);
            }
            
            // 창 닫기
            setTimeout(() => {
                if (authWin && !authWin.isDestroyed()) {
                    authWin.destroy();
                }
            }, 500);
        }
    };

    // 3중 네비게이션 핸들러
    authWin.webContents.on('will-redirect', (e, u) => handleResponse(u));
    authWin.webContents.on('will-navigate', (e, u) => handleResponse(u));
    authWin.webContents.on('did-get-redirect-request', (e, old, newUrl) => handleResponse(newUrl));

    authWin.loadURL(authUrl);

    authWin.on('closed', () => {
        authWin = null;
        authSession.clearStorageData();
    });
});
ipcMain.handle('login-with-account', async (event, accountIndex) => {
    const account = localAccounts[accountIndex];
    const mainWindow = BrowserWindow.getAllWindows()[0];
    
    // 🔥 계정별 전용 BrowserView 생성
    const accountView = new BrowserView({
        webPreferences: {
            partition: `persist:google-${account.email.replace(/[@.]/g, '_')}`  // 계정별 세션!
        }
    });
    
    mainWindow.addBrowserView(accountView);
    accountView.setBounds({ x: 0, y: 0, width: 1400, height: 900 });
    mainWindow.setTopBrowserView(accountView);
    
    // 쿠키 복원 (당신 코드 그대로!)
    const session = accountView.webContents.session;
    for (const cookie of account.cookies) {
        if (['SID','HSID','SSID','APISID','SAPISID','NID'].includes(cookie.name)) {
            session.cookies.set({
                url: 'https://accounts.google.com',
                name: cookie.name,
                value: cookie.value,
                path: '/'
            }).catch(() => {});
        }
    }
    
    accountView.webContents.loadURL('https://mail.google.com');
    console.log(`✅ ${account.email} BrowserView 자동로그인!`);
    return true;
});
ipcMain.handle('get-cookies-domain', async (event, domain) => {
    // 도메인을 포함하는 모든 쿠키를 가져옵니다.
    return await session.defaultSession.cookies.get({ domain: domain });
});
// 쿠키 값 가져오기 핸들러
// main.js의 쿠키 값 가져오기 핸들러 수정
// 쿠키 값 가져오기 핸들러 (이걸로 교체!)
// main.js 파일 하단 핸들러 부분
ipcMain.handle('get-cookie-value', async (event, { domain, name }) => {
    try {
        const targetSession = session.defaultSession;
        
        // 1. 이름으로만 검색해서 후보군을 다 가져옴
        const cookies = await targetSession.cookies.get({ name: name });
        
        // 2. 입력받은 도메인에서 앞의 점(.) 제거
        const cleanDomain = domain.startsWith('.') ? domain.substring(1) : domain;

        // 3. 후보군 중 도메인이 포함된 녀석을 정밀 검색
        const matched = cookies.find(c => {
            const cDomain = c.domain.startsWith('.') ? c.domain.substring(1) : c.domain;
            return cDomain === cleanDomain || cDomain.endsWith('.' + cleanDomain);
        });

        if (matched) {
            console.log(`✅ [지링스] 쿠키 로드 완료: ${name}`);
            return matched.value;
        }

        return "Cookie value not found in storage.";
    } catch (error) {
        console.error("Main Process Error:", error);
        return "Error: " + error.message;
    }
});
ipcMain.handle('save-cookie', async (event, { domain, name, value }) => {
    try {
        await session.defaultSession.cookies.set({
            url: `https://${domain.startsWith('.') ? domain.substring(1) : domain}`,
            name: name,
            value: value,
            domain: domain,
            path: '/',
            secure: true,
            httpOnly: true, // 구글 중요 쿠키는 보통 httpOnly입니다
            sameSite: 'no_restriction'
        });
        console.log(`✅ [지링스] 쿠키 저장 성공: ${name}`);
        return true;
    } catch (error) {
        console.error("Save Error:", error);
        return false;
    }
});