/**
 * gLinksWWW - QWebChannel 브릿지
 * 일렉트론 ipcRenderer를 PyQt6 QWebChannel로 대체
 */

// QWebChannel 로드 (PyQt6가 자동으로 제공)
let py_bridge = null;

// QWebChannel 초기화
new QWebChannel(qt.webChannelTransport, function(channel) {
    py_bridge = channel.objects.py_bridge;
    console.log("✅ [gLinks] QWebChannel 연결 완료!");
    
    // 초기 UI 로드
    if (window.onPyBridgeReady) {
        window.onPyBridgeReady();
    }
});

// 일렉트론 ipcRenderer API 에뮬레이션
window.electronAPI = {
    // === 클립보드 관련 ===
    saveClipboard: async (slot, content) => {
        if (py_bridge) {
            py_bridge.save_clipboard(slot, content);
        }
    },
    
    getClipboard: async (slot) => {
        if (py_bridge) {
            return await new Promise((resolve) => {
                py_bridge.get_clipboard(slot, (result) => {
                    resolve(result);
                });
            });
        }
        return "";
    },
    
    getAllClipboards: async () => {
        if (py_bridge) {
            return await new Promise((resolve) => {
                py_bridge.get_all_clipboards((result) => {
                    resolve(JSON.parse(result));
                });
            });
        }
        return {};
    },
    
    // === 탭 관리 ===
    createTab: async (url) => {
        if (py_bridge) {
            py_bridge.create_tab(url || "");
        }
    },
    
    switchTab: async (index) => {
        if (py_bridge) {
            py_bridge.switch_tab(index);
        }
    },
    
    closeTab: async (index) => {
        if (py_bridge) {
            py_bridge.close_tab(index);
        }
    },
    
    navigate: async (url) => {
        if (py_bridge) {
            py_bridge.navigate(url);
        }
    },
    
    goBack: async () => {
        if (py_bridge) {
            py_bridge.go_back();
        }
    },
    
    goForward: async () => {
        if (py_bridge) {
            py_bridge.go_forward();
        }
    },
    
    reload: async () => {
        if (py_bridge) {
            py_bridge.reload_page();
        }
    },
    
    getCurrentUrl: async () => {
        if (py_bridge) {
            return await new Promise((resolve) => {
                py_bridge.get_current_url((result) => {
                    resolve(result);
                });
            });
        }
        return "";
    },
    
    getCurrentTitle: async () => {
        if (py_bridge) {
            return await new Promise((resolve) => {
                py_bridge.get_current_title((result) => {
                    resolve(result);
                });
            });
        }
        return "새 탭";
    },
    
    // === 쿠키 관리 ===
    getCookieValue: async (data) => {
        if (py_bridge) {
            return await new Promise((resolve) => {
                py_bridge.get_cookie_value(data.domain, data.name, (result) => {
                    resolve(result);
                });
            });
        }
        return "";
    },
    
    saveCookie: async (data) => {
        if (py_bridge) {
            py_bridge.save_cookie(data.domain, data.name, data.value);
        }
    }
};

// Python에서 호출할 수 있는 전역 함수
window.updateTabsFromPython = function(data) {
    console.log("[gLinks] 탭 업데이트 수신:", data);
    
    // 기존 일렉트론 코드의 render-tabs 이벤트 에뮬레이션
    if (window.onTabsUpdated) {
        window.onTabsUpdated(data);
    }
};

console.log("✅ [gLinks] QWebChannel 브릿지 로드 완료!");
