import sys
import os
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QStackedWidget, QMessageBox, QFileDialog, QProgressDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineCookieStore, QWebEngineScript, QWebEngineDownloadRequest, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, pyqtSlot, QObject, pyqtSignal, QByteArray, QTimer, QStandardPaths
from PyQt6.QtGui import QKeySequence, QShortcut, QIcon
from PyQt6.QtNetwork import QNetworkCookie

# PyInstaller 실행 시 포함된 리소스 경로 보정
def resource_path(relative_path):
    """실행 파일 내부(임시 폴더)의 실제 경로를 찾아주는 함수"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    path = os.path.join(base_path, relative_path)
    # 디버그 로그 추가 (PyInstaller 빌드 시 경로 확인용)
    try:
        with open(os.path.join(base_path, "debug.log"), "a", encoding="utf-8") as f:
            f.write(f"resource_path: {relative_path} -> {path}, exists: {os.path.exists(path)}\n")
    except Exception:
        pass
    return path

try:
    import certifi
except Exception:
    certifi = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
from PyQt6.QtCore import QEvent # 한글 버그 수정용

# Windows 콘솔 인코딩 이슈로 print에서 앱이 죽지 않도록 보호
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 1. 자바스크립트와 통신할 '브릿지' 객체 정의
class GLinksCallHandler(QObject):
    # 시그널: JS에게 탭 목록을 보낼 때 사용
    tabs_updated = pyqtSignal(str)  # JSON 문자열로 전달
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
    # === 로깅 ===
    @pyqtSlot(str)
    def log_from_js(self, message):
        print(f"[JS Log]: {message}")
    
    # === 18슬롯 클립보드 ===
    @pyqtSlot(int, str)
    def save_clipboard(self, slot_num, content):
        """JS에서 클립보드 데이터를 저장"""
        self.main_window.multi_clipboard[str(slot_num)] = content
        self.main_window.save_clipboard_data()
        print(f"[gLinks] 슬롯 {slot_num} 저장됨: {content[:30]}...")
    
    @pyqtSlot(int, result=str)
    def get_clipboard(self, slot_num):
        """JS에서 클립보드 데이터를 가져옴"""
        return self.main_window.multi_clipboard.get(str(slot_num), "")
    
    @pyqtSlot(result=str)
    def get_all_clipboards(self):
        """모든 클립보드 데이터를 JSON으로 반환"""
        return json.dumps(self.main_window.multi_clipboard)
    
    @pyqtSlot(str)
    def delete_clipboard_slot(self, slot_key):
        """특정 클립보드 슬롯 삭제"""
        self.main_window.multi_clipboard[str(slot_key)] = ""
        self.main_window.save_clipboard_data()
    
    # === 탭 관리 ===
    @pyqtSlot(str)
    def create_tab(self, url):
        """새 탭 생성"""
        self.main_window.create_new_tab(url)
    
    @pyqtSlot(int)
    def switch_tab(self, index):
        """탭 전환"""
        self.main_window.switch_to_tab(index)
    
    @pyqtSlot(int)
    def close_tab(self, index):
        """탭 닫기"""
        self.main_window.close_tab(index)
    
    @pyqtSlot(str)
    def navigate(self, url):
        """현재 탭에서 URL로 이동"""
        self.main_window.navigate_current_tab(url)
    
    @pyqtSlot()
    def go_back(self):
        """뒤로 가기"""
        current_view = self.main_window.get_current_view()
        if current_view:
            current_view.back()
    
    @pyqtSlot()
    def go_forward(self):
        """앞으로 가기"""
        current_view = self.main_window.get_current_view()
        if current_view:
            current_view.forward()
    
    @pyqtSlot()
    def reload_page(self):
        """새로고침"""
        current_view = self.main_window.get_current_view()
        if current_view:
            current_view.reload()
    
    @pyqtSlot(result=str)
    def get_current_url(self):
        """현재 탭의 URL 반환"""
        current_view = self.main_window.get_current_view()
        if current_view:
            return current_view.url().toString()
        return ""
    
    @pyqtSlot(result=str)
    def get_current_title(self):
        """현재 탭의 제목 반환"""
        current_view = self.main_window.get_current_view()
        if current_view:
            return current_view.title()
        return "새 탭"
    
    # === 쿠키 관리 ===
    @pyqtSlot(str, str, result=str)
    def get_cookie_value(self, domain, name):
        """특정 도메인의 쿠키 값을 가져옴"""
        try:
            value = self.main_window.get_cookie_value_by_domain_and_name(domain, name)
            return value or ""
        except Exception as e:
            print(f"[gLinks] get_cookie_value 실패: {e}")
            return ""
    
    @pyqtSlot(str, str, str)
    def save_cookie(self, domain, name, value):
        """쿠키 저장"""
        self.main_window.set_cookie_value(domain, name, value)
    
    @pyqtSlot(str, result=str)
    def get_cookies_for_domain(self, domain):
        """특정 도메인의 모든 쿠키 조회"""
        try:
            return json.dumps(self.main_window.get_cookies_for_domain(domain), ensure_ascii=False)
        except Exception as e:
            print(f"[gLinks] get_cookies_for_domain failed: {e}")
            return "[]"
    
    @pyqtSlot(result=str)
    def get_cookies(self):
        """전체 쿠키와 현재 호스트 반환"""
        try:
            payload = {
                "cookies": self.main_window.get_all_cookies(),
                "currentHost": self.main_window.get_current_host(),
            }
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            print(f"[gLinks] get_cookies failed: {e}")
            return '{"cookies":[],"currentHost":""}'
    
    @pyqtSlot(str, result=bool)
    def delete_cookies(self, domain):
        """특정 도메인 쿠키 삭제"""
        try:
            return self.main_window.delete_cookies_by_domain(domain)
        except Exception as e:
            print(f"[gLinks] delete_cookies failed: {e}")
            return False
    
    @pyqtSlot(result=bool)
    def clear_all_cookies(self):
        """모든 쿠키 삭제"""
        try:
            return self.main_window.clear_all_cookies()
        except Exception as e:
            print(f"[gLinks] clear_all_cookies failed: {e}")
            return False


class GLinksWebPage(QWebEnginePage):
    """
    target=_blank / window.open 같은 '새 창' 요청을 처리합니다.
    기본은 메인창에서 새 탭을 열어 요청 URL을 로드합니다.
    """

    def __init__(self, main_window, web_view, profile):
        super().__init__(profile)
        self.main_window = main_window
        self.web_view = web_view
        self.newWindowRequested.connect(lambda request: self.main_window._open_url_in_new_tab(request.requestedUrl().toString()))

    def createWindow(self, type_):
        # QWebEnginePage가 새 창을 만들 때
        # 새 탭을 생성하고 해당 페이지 객체를 반환하여 바로 로드되도록 함.
        new_view = self.main_window.create_new_tab("", is_new_window_request=True)
        if new_view is not None:
            return new_view.page()
        return None

class GLinksMainWindow(QMainWindow):
    # 클래스 변수: 프로필을 전역에서 재사용
    _shared_profile = None
    
    def __init__(self):
        # 어떤 이유로든 QWidget이 생성되기 전에 QApplication이 없으면 즉시 생성
        # (사용자가 python main.py로 실행하거나 실행 경로가 꼬였을 때 방어용)
        if QApplication.instance() is None:
            QApplication(sys.argv)
        super().__init__()
        
        # === 데이터 저장 경로 ===
        self.user_data_dir = Path.home() / ".glinks_data"
        self.user_data_dir.mkdir(exist_ok=True)
        self.clipboard_file = self.user_data_dir / "multi-clipboard.json"
        self.cookie_file = self.user_data_dir / "cookies.json"  # 쿠키 저장 파일
        
        # === 18슬롯 클립보드 데이터 ===
        self.multi_clipboard = {}
        self.load_clipboard_data()
        
        # === 쿠키 데이터 ===
        self.cookie_data = []
        self.load_cookie_data()
        
        # === 탭 관련 데이터 ===
        self.tab_views = []  # QWebEngineView 리스트
        self.tab_icons = []  # 각 탭의 파비콘
        self.current_tab_index = 0
        
        # === 다운로드 관련 ===
        self.download_progress_dialog = None

        # === 메인 레이아웃 설정 ===
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # === 상단 UI 영역 (index.html: 주소창, 탭 등) ===
        self.ui_view = QWebEngineView()
        ui_path = resource_path("index.html")
        self.ui_view.setUrl(QUrl.fromLocalFile(ui_path))
        self.ui_view.setFixedHeight(79)
        self.ui_view.loadFinished.connect(lambda _: self.update_ui())

        # === 하단 메인 콘텐츠 영역 (다중 탭용 스택 위젯) ===
        self.tab_stack = QStackedWidget()
        
        # === 자바스크립트 연동 세팅 (QWebChannel) ===
        self.channel = QWebChannel()
        self.handler = GLinksCallHandler(self)
        self.channel.registerObject("py_bridge", self.handler)
        self.ui_view.page().setWebChannel(self.channel)
        
        # 첫 번째 탭 생성
        home_path = resource_path("home.html")
        self.create_new_tab(QUrl.fromLocalFile(home_path).toString())

        # 레이아웃에 배치 (위: UI, 아래: 탭 스택)
        self.layout.addWidget(self.ui_view)
        self.layout.addWidget(self.tab_stack)

        # === 윈도우 설정 ===
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setWindowTitle("gLinksWWW 2.0.0 - PyQt6 Powered")
        self.resize(1280, 800)

        # === 웹 프로필 설정 ===
        web_profile = self._get_or_create_shared_profile()
        self.cookie_store = web_profile.cookieStore()
        
        # 저장된 쿠키 데이터를 QWebEngineCookieStore에 설정
        self._load_cookies_to_store()
        
        # 쿠키 변경 감지 및 저장
        self.cookie_store.cookieAdded.connect(self._on_cookie_added)
        self.cookie_store.cookieRemoved.connect(self._on_cookie_removed)
        
        # 다운로드 요청 처리 (프로필 레벨)
        web_profile.downloadRequested.connect(self._handle_download_requested)
        web_profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36 gLinksWWW/2.0.0"
        )
        
        # 미디어 자동재생 허용 (일렉트론의 autoplay-policy)
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        settings = web_profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        # [꿀팁] 가속 및 성능 최적화 (이게 실제 사용자처럼 보이게 함)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)

        # 모든 페이지에 "자동화 브라우저"처럼 보이지 않게 최소 스푸핑 주입
        anti_bot_js = r"""
// gLinksWWW - PyQt6/QWebEngine 자동화 탐지 완화(최대 스푸핑)
(function() {
  try {
    // 기본 webdriver 제거
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  
  try {
    // 언어 설정
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR','ko','en-US','en'] });
  } catch (e) {}
  
  try {
    // 플랫폼 설정
    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
  } catch (e) {}
  
  try {
    // plugins 존재 보장
    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
  } catch (e) {}
  
  try {
    // WebGPU 더미
    Object.defineProperty(navigator, 'gpu', { get: () => ({ requestAdapter: () => Promise.resolve(null) }) });
  } catch (e) {}
  
  try {
    // Chrome 런타임 존재 보장
    window.chrome = window.chrome || { runtime: {} };
  } catch (e) {}
  
  try {
    // 추가적인 봇 감지 우회
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
    Object.defineProperty(navigator, 'cookieEnabled', { get: () => true });
    Object.defineProperty(navigator, 'onLine', { get: () => true });
  } catch (e) {}
  
  try {
    // Screen 속성들
    Object.defineProperty(screen, 'availWidth', { get: () => screen.width });
    Object.defineProperty(screen, 'availHeight', { get: () => screen.height });
    Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
    Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
  } catch (e) {}
})();
        """.strip()

        script = QWebEngineScript()
        script.setName("gLinksAntiBotSpoof")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)  # 더 일찍 실행
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        script.setSourceCode(anti_bot_js)
        web_profile.scripts().insert(script)
        
        # === 단축키 설정 ===
        self.setup_shortcuts()

        # IME 입력 후 커서 보정(디바운스)용 타이머
        self._caret_fix_timer = QTimer(self)
        self._caret_fix_timer.setSingleShot(True)
        self._pending_caret_fix = None  # QWebEngineView
        self._caret_fix_timer.timeout.connect(self._apply_caret_correction)
    
    @classmethod
    def _get_or_create_shared_profile(cls):
        """
        공유 프로필 생성 (싱글톤 패턴)
        LocalStorage, SessionStorage, IndexedDB가 영속되려면 
        프로필을 한 번만 생성해서 계속 재사용해야 함
        """
        if cls._shared_profile is None:
            cls._shared_profile = QWebEngineProfile()
            
            # 프로필 저장소 경로 설정
            user_data_dir = Path.home() / ".glinks_data"
            user_data_dir.mkdir(exist_ok=True)
            
            try:
                engine_dir = user_data_dir / "qtwebengine"
                engine_dir.mkdir(exist_ok=True)
                
                # LocalStorage, SessionStorage 저장 경로
                persistent_path = str(engine_dir / "storage")
                Path(persistent_path).mkdir(exist_ok=True)
                
                # 캐시 경로
                cache_path = str(engine_dir / "cache")
                Path(cache_path).mkdir(exist_ok=True)
                
                # [중요] 모든 인증 데이터를 한 폴더에 물리적으로 저장
                cls._shared_profile.setPersistentStoragePath(persistent_path)
                cls._shared_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
                
                # [중요] 캐시도 물리적으로 저장 (속도 향상 및 인증 유지)
                cls._shared_profile.setCachePath(cache_path)
                cls._shared_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
                
                print(f"[gLinks] 웹 프로필 초기화:")
                print(f"  - 저장소 경로: {persistent_path}")
                print(f"  - 캐시 경로: {cache_path}")
                
            except Exception as e:
                print(f"[gLinks] 프로필 저장소 설정 실패: {e}")
        
        return cls._shared_profile
        
    # === 클립보드 관련 메서드 ===
    def load_clipboard_data(self):
        """저장된 클립보드 데이터 불러오기"""
        try:
            if self.clipboard_file.exists():
                with open(self.clipboard_file, 'r', encoding='utf-8') as f:
                    self.multi_clipboard = json.load(f)
                print(f"[gLinks] clipboard loaded: {len(self.multi_clipboard)} slots")
        except Exception as e:
            print(f"[gLinks] failed to load clipboard: {e}")
            self.multi_clipboard = {}
    
    def save_clipboard_data(self):
        """클립보드 데이터를 파일에 저장"""
        try:
            with open(self.clipboard_file, 'w', encoding='utf-8') as f:
                json.dump(self.multi_clipboard, f, ensure_ascii=False, indent=2)
            print(f"[gLinks] 클립보드 데이터 저장 완료: {len(self.multi_clipboard)}개")
        except Exception as e:
            print(f"[gLinks] 클립보드 저장 실패: {e}")
    
    def load_cookie_data(self):
        """저장된 쿠키 데이터 불러오기"""
        try:
            if self.cookie_file.exists():
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    self.cookie_data = json.load(f)
                print(f"[gLinks] 쿠키 데이터 로드 완료: {len(self.cookie_data)}개")
        except Exception as e:
            print(f"[gLinks] 쿠키 로드 실패: {e}")
            self.cookie_data = []
    
    def save_cookie_data(self):
        """쿠키 데이터를 파일에 저장"""
        try:
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(self.cookie_data, f, ensure_ascii=False, indent=2)
            print(f"[gLinks] 쿠키 데이터 저장 완료: {len(self.cookie_data)}개")
        except Exception as e:
            print(f"[gLinks] 쿠키 저장 실패: {e}")
    
 
    def create_new_tab(self, url="", is_new_window_request=False):
        """새 탭 생성 (매개변수에 is_new_window_request 추가됨)"""
        web_view = QWebEngineView()
        
        # 1. 커스텀 페이지 설정 및 GC(메모리 삭제) 방지
        # web_view 객체 안에 페이지를 저장해서 함수가 끝나도 살아있게 함
        # 공유 프로필 사용 (LocalStorage, SessionStorage, IndexedDB 영속성 보장)
        web_view._page = GLinksWebPage(self, web_view, profile=self._get_or_create_shared_profile())
        web_view.setPage(web_view._page)
        
        # 2. 채널 및 시그널 설정 (화면 보이기 전에 연결!)
        web_view.page().setWebChannel(self.channel)
        
        # 3. 탭 리스트 및 스택에 추가
        self.tab_stack.addWidget(web_view)
        self.tab_views.append(web_view)
        self.tab_icons.append("default-icon.png")
        
        new_index = len(self.tab_views) - 1
        
        # 4. 이벤트 연결 (타이틀, URL 변경 등)
        web_view.titleChanged.connect(self.update_ui)
        web_view.urlChanged.connect(self.update_ui)
        # 아이콘 변경은 나중에 로직 보완
        # web_view.iconChanged.connect(lambda: self.update_tab_icon(new_index))
        
        # 링크 클릭 처리 (Ctrl+클릭으로 새 탭 열기 지원)
        web_view.page().navigationRequested.connect(lambda request: self._handle_navigation_requested(request))
        
        # 5. 새 탭으로 즉시 전환
        self.switch_to_tab(new_index)
        
        # 6. 만약 새 창 요청으로 들어온 거라면 URL 로드 없이 뷰만 반환
        if is_new_window_request:
            print(f"[gLinks] new tab created: tab {new_index}")
            return web_view
            
        # 7. URL 로드 로직 (비어있으면 홈으로)
        if not url:
            home_path = resource_path("home.html")
            url = QUrl.fromLocalFile(home_path).toString()
        
        # 주소 판별 및 이동
        if url.startswith(('http://', 'https://', 'file://')):
            web_view.setUrl(QUrl(url))
        elif os.path.exists(url):
            web_view.setUrl(QUrl.fromLocalFile(os.path.abspath(url)))
        else:
            # 검색어로 간주 (구글 검색)
            web_view.setUrl(QUrl("https://www.google.com/search?q=" + url))
            
        print(f"[gLinks] new tab created: {url}")
        self.update_ui()
        return web_view

    def _open_url_in_new_tab(self, url: str):
        """target=_blank/window.open 요청을 새 탭으로 연 뒤 이동"""
        try:
            if not url:
                return
            self.create_new_tab(url)
            print(f"[gLinks] new tab requested -> new tab created and loaded: {url}")
        except Exception as e:
            print(f"[gLinks] failed to open new tab: {e}")

    def eventFilter(self, source, event):
        """
        한글(IME) 입력 조합이 확정(commit)될 때 웹뷰 커서가 어긋나는 버그 대응.
        - create_new_tab에서 QWebEngineView에 installEventFilter(self)를 걸어둔 상태라,
          이벤트 필터는 여기(GLinksMainWindow)에 들어옵니다.
        """
        try:
            if source in self.tab_views and event.type() == QEvent.Type.InputMethod:
                # QInputMethodEvent: commitString()이 있으면 "확정 입력" 시점일 가능성이 큼
                commit = ""
                if hasattr(event, "commitString"):
                    commit = event.commitString()
                if commit:
                    self._pending_caret_fix = source
                    # DOM 반영 타이밍 확보를 위해 아주 짧게 지연
                    self._caret_fix_timer.start(10)
        except Exception:
            # 이벤트 필터는 절대 앱을 죽이면 안 됨
            pass
        return super().eventFilter(source, event)

    def _apply_caret_correction(self):
        """activeElement(input/textarea)의 caret을 1칸 뒤로 보정"""
        view = self._pending_caret_fix
        self._pending_caret_fix = None
        if not view:
            return
        try:
            page = view.page()
            if not page:
                return
            js = r"""
(function(){
  const el = document.activeElement;
  if (!el) return;
  const tag = (el.tagName || '').toUpperCase();
  if (tag !== 'INPUT' && tag !== 'TEXTAREA') return;
  try {
    if (typeof el.setSelectionRange !== 'function') return;
    const start = (typeof el.selectionStart === 'number') ? el.selectionStart : null;
    const end = (typeof el.selectionEnd === 'number') ? el.selectionEnd : null;
    if (start === null || end === null) return;
    // "한 칸 앞으로" 밀리는 케이스 대응: caret이 증가된 상태로 commit될 때 -1 보정
    if (start === end && start > 0) {
      const pos = start - 1;
      el.focus();
      el.setSelectionRange(pos, pos);
    }
  } catch(e) {}
})();
            """.strip()
            page.runJavaScript(js)
        except Exception:
            pass
  
    def switch_to_tab(self, index):
        """탭 전환"""
        if 0 <= index < len(self.tab_views):
            self.current_tab_index = index
            self.tab_stack.setCurrentIndex(index)
            self.update_ui()
            print(f"[gLinks] tab changed: {index}")
    
    def _handle_navigation_requested(self, request):
        """네비게이션 요청 처리: 링크 클릭 시 Ctrl+클릭으로 새 탭 열기"""
        if request.navigationType() == QWebEnginePage.NavigationType.NavigationTypeLinkClicked and request.isMainFrame():
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self.create_new_tab(request.url().toString())
                print(f"[gLinks] Ctrl+click: new tab created - {request.url().toString()}")
                request.reject()  # 네비게이션 거부
            else:
                print(f"[gLinks] link clicked: navigating to current tab - {request.url().toString()}")
                request.accept()  # 네비게이션 허용
        else:
            request.accept()    
    def _handle_download_requested(self, download):
        """다운로드 요청 처리 - 폴더 선택 + 진행바 표시"""
        try:
            # 파일명 가져오기
            filename = download.downloadFileName()
            if not filename:
                filename = "download"
            
            # 기본 다운로드 폴더
            default_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            if not default_dir:
                default_dir = str(Path.home() / "Downloads")
            
            # 저장 경로 선택 다이얼로그
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "다운로드 위치 선택",
                os.path.join(default_dir, filename),
                "All Files (*.*)"
            )
            
            if not save_path:  # 취소됨
                download.cancel()
                return
            
            # 선택된 경로로 다운로드 설정
            download.setDownloadDirectory(os.path.dirname(save_path))
            download.setDownloadFileName(os.path.basename(save_path))
            
            # 진행바 다이얼로그 생성
            from PyQt6.QtCore import Qt
            self.download_progress_dialog = QProgressDialog(
                f"'{filename}' 다운로드 중...",
                "취소",
                0, 100, self
            )
            self.download_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.download_progress_dialog.setAutoClose(True)
            self.download_progress_dialog.setAutoReset(True)
            self.download_progress_dialog.canceled.connect(lambda: download.cancel())
            
            # 진행 상황 연결 (QWebEngineDownloadRequest 속성 기반)
            download.receivedBytesChanged.connect(lambda: self._on_download_progress(download))
            download.totalBytesChanged.connect(lambda: self._on_download_progress(download))
            download.stateChanged.connect(lambda state: self._on_download_state_changed(download, state))
            
            # 진행바 표시
            self.download_progress_dialog.show()
            
            # 다운로드 시작
            download.accept()
            print(f"[gLinks] 다운로드 시작: {filename} -> {save_path}")
            
        except Exception as e:
            print(f"[gLinks] 다운로드 처리 실패: {e}")
            QMessageBox.warning(self, "다운로드 실패", f"다운로드를 시작할 수 없습니다:\n{str(e)}")
            if self.download_progress_dialog:
                self.download_progress_dialog.close()
    
    def _on_download_progress(self, download):
        """다운로드 진행 상황 - 진행바 업데이트"""
        if not self.download_progress_dialog:
            return
        total = download.totalBytes()
        received = download.receivedBytes()
        if total > 0:
            progress = int((received / total) * 100)
            self.download_progress_dialog.setValue(progress)
            self.download_progress_dialog.setLabelText(
                f"download '{download.downloadFileName()}' ({progress}%)"
            )
            print(f"[gLinks] 다운로드 진행: {download.downloadFileName()} - {progress}% ({received}/{total} bytes)")

    def _on_download_state_changed(self, download, state):
        """다운로드 상태 변경 처리"""
        if self.download_progress_dialog and download.isFinished():
            self.download_progress_dialog.close()
            self.download_progress_dialog = None

        try:
            if download.isFinished():
                if download.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                    QMessageBox.information(
                        self,
                        "다운로드 성공",
                        f"'{download.downloadFileName()}' files are succesfully downloaded."
                    )
                    print(f"[gLinks] 다운로드 완료: {download.downloadFileName()}")
                elif download.state() == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
                    reason = download.interruptReason()
                    QMessageBox.warning(
                        self,
                        "다운로드 실패",
                        f"'{download.downloadFileName()}' downloads are failed.\nreason: {reason}"
                    )
                    print(f"[gLinks] 다운로드 실패: {download.downloadFileName()} - {reason}")
        except Exception as e:
            print(f"[gLinks] 다운로드 상태 처리 실패: {e}")
            if self.download_progress_dialog:
                self.download_progress_dialog.close()
                self.download_progress_dialog = None

    def close_tab(self, index):
        """탭 닫기"""
        if len(self.tab_views) <= 1:
            print("[gLinks] last tab cannot close")
            return
        
        if 0 <= index < len(self.tab_views):
            # 위젯 제거
            widget = self.tab_views[index]
            self.tab_stack.removeWidget(widget)
            widget.deleteLater()
            
            # 리스트에서 제거
            self.tab_views.pop(index)
            self.tab_icons.pop(index)
            
            # 현재 탭 인덱스 조정
            if self.current_tab_index >= len(self.tab_views):
                self.current_tab_index = len(self.tab_views) - 1
            
            self.switch_to_tab(self.current_tab_index)
            print(f"[gLinks] tab closed: {index}")
    
    def navigate_current_tab(self, url):
        """현재 탭에서 URL로 이동"""
        current_view = self.get_current_view()
        if current_view:
            # http:// 또는 https://가 없으면 추가
            if not url.startswith(('http://', 'https://', 'file://')):
                if '.' in url:
                    url = 'https://' + url
                else:
                    url = 'https://www.google.com/search?q=' + url
            
            current_view.setUrl(QUrl(url))
            print(f"[gLinks] 네비게이션: {url}")
    
    def get_current_view(self):
        """현재 활성 탭의 QWebEngineView 반환"""
        if 0 <= self.current_tab_index < len(self.tab_views):
            return self.tab_views[self.current_tab_index]
        return None
    
    def update_tab_icon(self, index):
        """탭 아이콘 업데이트"""
        if 0 <= index < len(self.tab_views):
            icon = self.tab_views[index].icon()
            # 아이콘을 파일로 저장하거나 base64로 변환하여 JS에 전달
            # 간단하게 기본 아이콘 사용
            self.tab_icons[index] = "default-icon.png"
            self.update_ui()
    
    def update_ui(self):
        """UI 업데이트 (탭 목록을 JS로 전송)"""
        tab_list = []
        for i, view in enumerate(self.tab_views):
            tab_list.append({
                "title": view.title() or "새 탭",
                "url": view.url().toString(),
                "icon": self.tab_icons[i]
            })
        
        # JS로 탭 목록 전송
        data = {
            "tabList": tab_list,
            "activeIndex": self.current_tab_index
        }
        
        # QWebChannel을 통해 JS에 데이터 전송
        self.ui_view.page().runJavaScript(
            f"if (window.updateTabsFromPython) {{ window.updateTabsFromPython({json.dumps(data)}); }}"
        )
    
    # === 쿠키 관련 메서드 ===
    def _to_text(self, value):
        """QNetworkCookie 필드 값을 안전하게 문자열로 변환"""
        if isinstance(value, QByteArray):
            return bytes(value).decode("utf-8", errors="ignore")
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            return value
        return str(value) if value is not None else ""

    def _cookie_key(self, cookie):
        domain = self._to_text(cookie.domain())
        path = self._to_text(cookie.path())
        name = self._to_text(cookie.name())
        return (domain, path, name)
    
    def _cookie_to_dict(self, cookie):
        cookie_dict = {
            "name": self._to_text(cookie.name()),
            "value": self._to_text(cookie.value()),
            "domain": self._to_text(cookie.domain()),  # 원본 도메인 유지 (.google.com 포함)
            "path": self._to_text(cookie.path()) or "/",
            "secure": bool(cookie.isSecure()),
            "httpOnly": bool(cookie.isHttpOnly()),
        }
        # SameSite 속성 저장
        try:
            sameSite = cookie.sameSitePolicy()
            # 0=Default, 1=Lax, 2=Strict, 3=None
            sameSite_map = {0: "Default", 1: "Lax", 2: "Strict", 3: "None"}
            cookie_dict["sameSite"] = sameSite_map.get(int(sameSite), "Default")
        except Exception:
            pass
        
        # 만료 시간 추가 (세션 쿠키가 아니면)
        if cookie.expirationDate().isValid():
            cookie_dict["expirationDate"] = cookie.expirationDate().toSecsSinceEpoch()
        return cookie_dict
    
    def _normalize_domain(self, domain: str):
        if not domain:
            return ""
        return domain[1:] if domain.startswith(".") else domain
    
    def _domain_matches(self, cookie_domain: str, target_domain: str):
        cd = self._normalize_domain(cookie_domain)
        td = self._normalize_domain(target_domain)
        return cd == td or cd.endswith("." + td)
    
    def _load_cookies_to_store(self):
        """저장된 쿠키 데이터를 QWebEngineCookieStore에 로드"""
        try:
            for cookie_dict in self.cookie_data:
                cookie = QNetworkCookie()
                cookie.setName(cookie_dict.get("name", "").encode("utf-8"))
                cookie.setValue(cookie_dict.get("value", "").encode("utf-8"))
                
                domain = cookie_dict.get("domain", "")
                cookie.setDomain(domain)  # 원본 도메인 유지 (.google.com 포함)
                cookie.setPath(cookie_dict.get("path", "/"))
                cookie.setSecure(cookie_dict.get("secure", False))
                cookie.setHttpOnly(cookie_dict.get("httpOnly", False))
                
                # SameSite 속성 로드
                sameSite_str = cookie_dict.get("sameSite", "Default")
                try:
                    if sameSite_str == "Lax":
                        cookie.setSameSitePolicy(QNetworkCookie.SameSitePolicy.Lax)
                    elif sameSite_str == "Strict":
                        cookie.setSameSitePolicy(QNetworkCookie.SameSitePolicy.Strict)
                    elif sameSite_str == "None":
                        cookie.setSameSitePolicy(QNetworkCookie.SameSitePolicy.None_)
                except Exception:
                    pass
                
                # 만료 시간 설정 (없으면 세션 쿠키)
                if "expirationDate" in cookie_dict:
                    from PyQt6.QtCore import QDateTime
                    expiration = QDateTime.fromSecsSinceEpoch(int(cookie_dict["expirationDate"]))
                    cookie.setExpirationDate(expiration)
                
                # Origin 설정: 도메인을 정규화해서 사용
                # .google.com -> google.com으로 정규화
                normalized_domain = self._normalize_domain(domain) or domain
                origin = QUrl(f"https://{normalized_domain}")
                self.cookie_store.setCookie(cookie, origin)
                
            print(f"[gLinks] 쿠키 스토어에 로드 완료: {len(self.cookie_data)}개")
        except Exception as e:
            print(f"[gLinks] 쿠키 스토어 로드 실패: {e}")
    
    def _on_cookie_added(self, cookie):
        """쿠키 추가 시 파일에 저장"""
        try:
            cookie_dict = self._cookie_to_dict(cookie)
            # 중복 제거
            self.cookie_data = [c for c in self.cookie_data if not (
                c.get("name") == cookie_dict["name"] and 
                c.get("domain") == cookie_dict["domain"] and 
                c.get("path") == cookie_dict["path"]
            )]
            self.cookie_data.append(cookie_dict)
            self.save_cookie_data()
        except Exception as e:
            print(f"[gLinks] 쿠키 추가 처리 실패: {e}")
    
    def _on_cookie_removed(self, cookie):
        """쿠키 제거 시 파일에서 삭제"""
        try:
            cookie_dict = self._cookie_to_dict(cookie)
            self.cookie_data = [c for c in self.cookie_data if not (
                c.get("name") == cookie_dict["name"] and 
                c.get("domain") == cookie_dict["domain"] and 
                c.get("path") == cookie_dict["path"]
            )]
            self.save_cookie_data()
        except Exception as e:
            print(f"[gLinks] 쿠키 제거 처리 실패: {e}")
    
    def get_current_host(self):
        current_view = self.get_current_view()
        if not current_view:
            return ""
        return current_view.url().host() or ""
    
    def get_all_cookies(self):
        # 파일에 저장된 쿠키 데이터 반환
        return self.cookie_data
    
    def get_cookies_for_domain(self, domain: str):
        cookies = []
        for cookie_dict in self.cookie_data:
            cookie_domain = cookie_dict.get("domain", "")
            if self._domain_matches(cookie_domain, domain):
                cookies.append(cookie_dict)
        return cookies
    
    def get_cookie_value_by_domain_and_name(self, domain: str, name: str):
        for cookie_dict in self.cookie_data:
            cookie_name = cookie_dict.get("name", "")
            cookie_domain = cookie_dict.get("domain", "")
            if cookie_name == name and self._domain_matches(cookie_domain, domain):
                return cookie_dict.get("value", "")
        return ""
    
    def set_cookie_value(self, domain: str, name: str, value: str):
        safe_domain = self._normalize_domain(domain)
        if not safe_domain:
            return
        
        # 파일 데이터에 추가/업데이트
        cookie_dict = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": "/",
            "secure": True,
            "httpOnly": True,
        }
        
        # 중복 제거 후 추가
        self.cookie_data = [c for c in self.cookie_data if not (
            c.get("name") == name and c.get("domain") == domain and c.get("path") == "/"
        )]
        self.cookie_data.append(cookie_dict)
        self.save_cookie_data()
        
        # QWebEngineCookieStore에도 설정
        cookie = QNetworkCookie()
        cookie.setName(name.encode("utf-8"))
        cookie.setValue(value.encode("utf-8"))
        cookie.setDomain(domain)
        cookie.setPath("/")
        cookie.setSecure(True)
        cookie.setHttpOnly(True)
        origin = QUrl(f"https://{safe_domain}")
        self.cookie_store.setCookie(cookie, origin)
    
    def delete_cookies_by_domain(self, domain: str):
        # 파일 데이터에서 삭제
        self.cookie_data = [c for c in self.cookie_data if not self._domain_matches(c.get("domain", ""), domain)]
        self.save_cookie_data()
        
        # QWebEngineCookieStore에서도 삭제 (기존 로직 재사용)
        targets = []
        for cookie_dict in self.cookie_data:
            cookie_domain = cookie_dict.get("domain", "")
            if self._domain_matches(cookie_domain, domain):
                qc = QNetworkCookie()
                qc.setName(str(cookie_dict.get("name", "")).encode("utf-8"))
                qc.setValue(str(cookie_dict.get("value", "")).encode("utf-8"))
                qc.setDomain(cookie_domain)
                qc.setPath(str(cookie_dict.get("path", "/")) or "/")
                qc.setSecure(bool(cookie_dict.get("secure", False)))
                qc.setHttpOnly(bool(cookie_dict.get("httpOnly", False)))
                targets.append(qc)
        for qc in targets:
            self.cookie_store.deleteCookie(qc)
        return True
    
    def clear_all_cookies(self):
        self.cookie_data.clear()
        self.save_cookie_data()
        self.cookie_store.deleteAllCookies()
        return True
    
    def setup_shortcuts(self):
        """단축키 설정"""
        # 멀티 클립보드 전용 단축키(앱 포커스 있을 때만 동작)
        self._multi_clipboard_shortcuts = []
        keys = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8']

        def _store_clipboard(slot_key: str):
            # 실제 Copy/Cut 이후 클립보드가 갱신된 뒤 저장하기 위해 약간 지연
            try:
                content = QApplication.clipboard().text()
                if content is None:
                    content = ""
                self.multi_clipboard[str(slot_key)] = content
                self.save_clipboard_data()
                print(f"[gLinks] 슬롯 {slot_key} 저장됨: {content[:30]}...")
            except Exception as e:
                print(f"[gLinks] 클립보드 저장 실패: {e}")

        def _copy_to_slot(slot_key: str):
            view = self.get_current_view()
            if not view:
                return
            try:
                view.page().triggerAction(QWebEnginePage.WebAction.Copy)
                QTimer.singleShot(100, lambda: _store_clipboard(slot_key))
            except Exception as e:
                print(f"[gLinks] Copy 실패: {e}")

        def _cut_to_slot(slot_key: str):
            view = self.get_current_view()
            if not view:
                return
            try:
                view.page().triggerAction(QWebEnginePage.WebAction.Cut)
                QTimer.singleShot(100, lambda: _store_clipboard(slot_key))
            except Exception as e:
                print(f"[gLinks] Cut 실패: {e}")

        def _paste_from_slot(slot_key: str):
            view = self.get_current_view()
            if not view:
                return
            content = self.multi_clipboard.get(str(slot_key), "")
            if not content:
                return
            try:
                QApplication.clipboard().setText(content)
                view.page().triggerAction(QWebEnginePage.WebAction.Paste)
            except Exception as e:
                print(f"[gLinks] Paste 실패: {e}")

        # 1) Ctrl/Cmd + Shift + key => Copy
        for k in keys:
            seq = QKeySequence(f"Ctrl+Shift+{k}")
            sc = QShortcut(seq, self, lambda kk=k: _copy_to_slot(kk))
            self._multi_clipboard_shortcuts.append(sc)

        # 2) Alt + Shift + key => Cut
        for k in keys:
            seq = QKeySequence(f"Alt+Shift+{k}")
            sc = QShortcut(seq, self, lambda kk=k: _cut_to_slot(kk))
            self._multi_clipboard_shortcuts.append(sc)

        # 3) Ctrl/Cmd + Alt + key => Paste
        for k in keys:
            seq = QKeySequence(f"Ctrl+Alt+{k}")
            sc = QShortcut(seq, self, lambda kk=k: _paste_from_slot(kk))
            self._multi_clipboard_shortcuts.append(sc)

        # Ctrl+T: 새 탭
        QShortcut(QKeySequence("Ctrl+T"), self, lambda: self.create_new_tab(""))
        
        # Ctrl+W: 탭 닫기
        QShortcut(QKeySequence("Ctrl+W"), self, 
                  lambda: self.close_tab(self.current_tab_index))
        
        # Ctrl+R: 새로고침
        QShortcut(QKeySequence("Ctrl+R"), self, self._reload_current_tab)
        
        # F5: 새로고침
        QShortcut(QKeySequence("F5"), self, self._reload_current_tab)
        
        # Alt+Left: 뒤로
        QShortcut(QKeySequence("Alt+Left"), self, self._go_back)
        
        # Alt+Right: 앞으로
        QShortcut(QKeySequence("Alt+Right"), self, self._go_forward)
    
    def _reload_current_tab(self):
        """현재 탭 새로고침"""
        view = self.get_current_view()
        if view:
            view.reload()
    
    def _go_back(self):
        """뒤로 가기"""
        view = self.get_current_view()
        if view:
            view.back()
    
    def _go_forward(self):
        """앞으로 가기"""
        view = self.get_current_view()
        if view:
            view.forward()
    
    def closeEvent(self, event):
        """앱 종료 시 쿠키 저장 강제"""
        try:
            # 쿠키 저장 강제
            self.save_cookie_data()
            print("[gLinks] 앱 종료 - 쿠키 저장 완료")
        except Exception as e:
            print(f"[gLinks] 쿠키 저장 실패: {e}")
        event.accept()

if __name__ == "__main__":
    if load_dotenv:
        load_dotenv() # .env 파일 로드
    # SSL 인증서 경로 강제 설정 (certifi 활용)
    if certifi:
        os.environ['SSL_CERT_FILE'] = certifi.where()
    app = QApplication.instance() or QApplication(sys.argv)
    window = GLinksMainWindow()
    window.show()
    sys.exit(app.exec())
    
  