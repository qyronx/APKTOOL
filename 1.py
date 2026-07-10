# server.py - APKWorkshop NullByte 백엔드 (완전 수정)
# 실행: python server.py (포트 10000)

import os
import sys
import platform
import subprocess
import shutil
import json
import uuid
import zipfile
import tempfile
import urllib.request
import tarfile
import time
import re
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ========== 경로 설정 ==========
SERVER_DIR = Path(__file__).parent.absolute()
BASE_DIR = SERVER_DIR / "workspace"
BASE_DIR.mkdir(exist_ok=True, mode=0o755)

TOOLS_DIR = SERVER_DIR / "tools"
TOOLS_DIR.mkdir(exist_ok=True, mode=0o755)

# ========== Java 자동 설치 ==========
def is_java_installed():
    java = shutil.which("java")
    if java:
        try:
            result = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True
        except:
            pass
    return False

def get_java_version():
    java = shutil.which("java")
    if java:
        try:
            result = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=5)
            output = result.stderr + result.stdout
            match = re.search(r'version "(\d+)', output)
            if match:
                return int(match.group(1))
        except:
            pass
    return 0

def install_java_windows():
    print("[*] Windows용 Java 다운로드 중...")
    java_dir = TOOLS_DIR / "java"
    java_dir.mkdir(exist_ok=True)
    
    java_zip = TOOLS_DIR / "openjdk.zip"
    try:
        url = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.9%2B9/OpenJDK17U-jdk_x64_windows_hotspot_17.0.9_9.zip"
        urllib.request.urlretrieve(url, java_zip)
        
        with zipfile.ZipFile(java_zip, 'r') as zf:
            zf.extractall(java_dir)
        java_zip.unlink()
        
        jdk_dirs = [d for d in java_dir.iterdir() if d.is_dir() and d.name.startswith("jdk")]
        if jdk_dirs:
            jdk_home = jdk_dirs[0]
            os.environ["JAVA_HOME"] = str(jdk_home)
            bin_path = jdk_home / "bin"
            os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ.get("PATH", "")
            print(f"[+] Java 설치 완료: {jdk_home}")
            return True
    except Exception as e:
        print(f"[!] Java 설치 실패: {e}")
        try:
            alt_url = "https://corretto.aws/downloads/latest/amazon-corretto-17-x64-windows-jdk.zip"
            urllib.request.urlretrieve(alt_url, java_zip)
            with zipfile.ZipFile(java_zip, 'r') as zf:
                zf.extractall(java_dir)
            java_zip.unlink()
            jdk_dirs = [d for d in java_dir.iterdir() if d.is_dir() and d.name.startswith("amazon")]
            if jdk_dirs:
                jdk_home = jdk_dirs[0]
                os.environ["JAVA_HOME"] = str(jdk_home)
                bin_path = jdk_home / "bin"
                os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ.get("PATH", "")
                print(f"[+] Java 설치 완료: {jdk_home}")
                return True
        except Exception as e2:
            print(f"[!] 대체 Java 설치도 실패: {e2}")
    return False

def install_java_linux():
    print("[*] Linux용 Java 다운로드 중...")
    java_dir = TOOLS_DIR / "java"
    java_dir.mkdir(exist_ok=True)
    
    java_tar = TOOLS_DIR / "openjdk.tar.gz"
    try:
        url = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.9%2B9/OpenJDK17U-jdk_x64_linux_hotspot_17.0.9_9.tar.gz"
        urllib.request.urlretrieve(url, java_tar)
        
        with tarfile.open(java_tar, "r:gz") as tar:
            tar.extractall(java_dir)
        java_tar.unlink()
        
        jdk_dirs = [d for d in java_dir.iterdir() if d.is_dir() and d.name.startswith("jdk")]
        if jdk_dirs:
            jdk_home = jdk_dirs[0]
            os.environ["JAVA_HOME"] = str(jdk_home)
            bin_path = jdk_home / "bin"
            os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ.get("PATH", "")
            for f in bin_path.iterdir():
                f.chmod(0o755)
            print(f"[+] Java 설치 완료: {jdk_home}")
            return True
    except Exception as e:
        print(f"[!] Java 설치 실패: {e}")
    return False

def install_java_mac():
    print("[*] Mac용 Java 다운로드 중...")
    java_dir = TOOLS_DIR / "java"
    java_dir.mkdir(exist_ok=True)
    
    java_tar = TOOLS_DIR / "openjdk.tar.gz"
    try:
        url = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.9%2B9/OpenJDK17U-jdk_x64_mac_hotspot_17.0.9_9.tar.gz"
        urllib.request.urlretrieve(url, java_tar)
        
        with tarfile.open(java_tar, "r:gz") as tar:
            tar.extractall(java_dir)
        java_tar.unlink()
        
        jdk_dirs = [d for d in java_dir.iterdir() if d.is_dir() and d.name.startswith("jdk")]
        if jdk_dirs:
            jdk_home = jdk_dirs[0]
            os.environ["JAVA_HOME"] = str(jdk_home)
            bin_path = jdk_home / "bin"
            os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ.get("PATH", "")
            for f in bin_path.iterdir():
                f.chmod(0o755)
            print(f"[+] Java 설치 완료: {jdk_home}")
            return True
    except Exception as e:
        print(f"[!] Java 설치 실패: {e}")
    return False

def ensure_java():
    if is_java_installed():
        ver = get_java_version()
        print(f"[*] Java 발견 (버전 {ver})")
        if ver >= 11:
            return True
        else:
            print(f"[!] Java 버전이 낮음 (11+ 필요)")
    
    print("[*] Java가 설치되어 있지 않거나 버전이 낮음. 자동 설치 시작...")
    
    system = platform.system().lower()
    success = False
    
    if system == 'windows':
        success = install_java_windows()
    elif system == 'linux':
        success = install_java_linux()
    elif system == 'darwin':
        success = install_java_mac()
    else:
        print(f"[!] 지원하지 않는 OS: {system}")
    
    if success:
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            bin_path = Path(java_home) / "bin"
            os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ.get("PATH", "")
        return True
    else:
        print("[!] Java 자동 설치 실패. 수동으로 Java 11+ 설치 필요")
        return False

# ========== index.html 서빙 ==========
@app.route('/')
def serve_index():
    index_path = SERVER_DIR / "index.html"
    if index_path.exists():
        return send_from_directory(str(SERVER_DIR), "index.html")
    else:
        return jsonify({"error": "index.html 파일이 서버 디렉토리에 없습니다."}), 404

@app.route('/<path:filename>')
def serve_static(filename):
    if filename.startswith('api/'):
        return jsonify({"error": "API 엔드포인트가 아닙니다"}), 404
    file_path = SERVER_DIR / filename
    if file_path.exists() and file_path.is_file():
        return send_from_directory(str(SERVER_DIR), filename)
    return jsonify({"error": "파일 없음"}), 404

# ========== 도구 존재 여부 확인 ==========
def is_tool_installed(tool_name):
    if shutil.which(tool_name):
        return True
    tool_path = TOOLS_DIR / tool_name
    if tool_path.exists():
        return True
    if platform.system().lower() == 'windows':
        for ext in ['.bat', '.exe', '.cmd']:
            tool_path = TOOLS_DIR / f"{tool_name}{ext}"
            if tool_path.exists():
                return True
    if tool_name == "jadx":
        jadx_bin = TOOLS_DIR / "jadx" / "bin" / "jadx"
        if jadx_bin.exists():
            return True
        jadx_bin = TOOLS_DIR / "jadx" / "bin" / "jadx.bat"
        if jadx_bin.exists():
            return True
    return False

# ========== 자동 의존성 설치 ==========
def install_dependencies():
    print("[*] 의존성 설치 시작...")
    print(f"[*] 서버 디렉토리: {SERVER_DIR}")
    print(f"[*] 도구 디렉토리: {TOOLS_DIR}")
    
    ensure_java()
    
    system = platform.system().lower()
    is_windows = system == 'windows'
    is_linux = system == 'linux'
    is_mac = system == 'darwin'

    # apktool 설치 (기존과 동일)
    if not is_tool_installed("apktool"):
        print("[*] apktool 다운로드 중...")
        try:
            if is_windows:
                urllib.request.urlretrieve(
                    "https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/windows/apktool.bat",
                    TOOLS_DIR / "apktool.bat"
                )
                urllib.request.urlretrieve(
                    "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar",
                    TOOLS_DIR / "apktool.jar"
                )
            else:
                urllib.request.urlretrieve(
                    "https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/linux/apktool",
                    TOOLS_DIR / "apktool"
                )
                (TOOLS_DIR / "apktool").chmod(0o755)
                urllib.request.urlretrieve(
                    "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar",
                    TOOLS_DIR / "apktool.jar"
                )
            print("[+] apktool 설치 완료")
        except Exception as e:
            print(f"[!] apktool 설치 실패: {e}")
    else:
        print("[*] apktool 이미 설치됨")

    # ★★★ jadx 설치 수정 ★★★
    if not is_tool_installed("jadx"):
        print("[*] jadx 다운로드 중...")
        try:
            zip_path = TOOLS_DIR / "jadx.zip"
            urllib.request.urlretrieve(
                "https://github.com/skylot/jadx/releases/download/v1.4.7/jadx-1.4.7.zip",
                zip_path
            )
            
            # jadx 전용 디렉토리에 압축 해제
            jadx_dir = TOOLS_DIR / "jadx"
            jadx_dir.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(jadx_dir)
            zip_path.unlink()
            
            # 실행 권한 설정
            if is_linux or is_mac:
                bin_dir = jadx_dir / "bin"
                if bin_dir.exists():
                    for f in bin_dir.iterdir():
                        if f.is_file():
                            f.chmod(0o755)
            
            # PATH에 jadx/bin 추가
            jadx_bin = TOOLS_DIR / "jadx" / "bin"
            if jadx_bin.exists():
                os.environ["PATH"] = str(jadx_bin) + os.pathsep + os.environ.get("PATH", "")
            
            print("[+] jadx 설치 완료")
        except Exception as e:
            print(f"[!] jadx 설치 실패: {e}")
    else:
        print("[*] jadx 이미 설치됨")

    # Windows SDK 도구 (기존과 동일)
    if is_windows:
        tools_to_download = {
            "aapt2": "https://dl.google.com/android/repository/aapt2-windows-8.0.0-10154469.zip",
            "zipalign": "https://dl.google.com/android/repository/zipalign-windows-8.0.0-10154469.zip",
            "apksigner": "https://dl.google.com/android/repository/apksigner-windows-8.0.0-10154469.zip"
        }
        for tool_name, url in tools_to_download.items():
            if not is_tool_installed(tool_name):
                print(f"[*] {tool_name} 다운로드 중...")
                try:
                    zip_path = TOOLS_DIR / f"{tool_name}.zip"
                    urllib.request.urlretrieve(url, zip_path)
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        zf.extractall(TOOLS_DIR)
                    zip_path.unlink()
                    for exe in TOOLS_DIR.glob(f"**/{tool_name}.exe"):
                        shutil.move(str(exe), str(TOOLS_DIR / f"{tool_name}.exe"))
                    print(f"[+] {tool_name} 설치 완료")
                except Exception as e:
                    print(f"[!] {tool_name} 설치 실패: {e}")
            else:
                print(f"[*] {tool_name} 이미 설치됨")
    
    # PATH 업데이트
    os.environ["PATH"] = str(TOOLS_DIR) + os.pathsep + os.environ.get("PATH", "")
    jadx_bin = TOOLS_DIR / "jadx" / "bin"
    if jadx_bin.exists():
        os.environ["PATH"] = str(jadx_bin) + os.pathsep + os.environ["PATH"]
    
    # 디버그 키스토어 (기존과 동일)
    debug_keystore = TOOLS_DIR / "debug.keystore"
    if not debug_keystore.exists():
        print("[*] 디버그 키스토어 생성 중...")
        try:
            keytool_path = shutil.which("keytool")
            if keytool_path:
                subprocess.run([
                    keytool_path, "-genkey", "-v",
                    "-keystore", str(debug_keystore),
                    "-alias", "androiddebugkey",
                    "-keyalg", "RSA",
                    "-keysize", "2048",
                    "-validity", "10000",
                    "-storepass", "android",
                    "-keypass", "android",
                    "-dname", "CN=Android Debug, O=Android, C=US"
                ], check=False, timeout=30)
                print("[+] 디버그 키스토어 생성 완료")
            else:
                print("[!] keytool 없음")
        except Exception as e:
            print(f"[!] 키스토어 생성 실패: {e}")
    
    print("[+] 의존성 설치 완료")

# ========== 도구 경로 헬퍼 ==========
def get_tool_path(tool_name):
    if shutil.which(tool_name):
        return Path(shutil.which(tool_name))
    
    tool_path = TOOLS_DIR / tool_name
    if tool_path.exists():
        return tool_path
    
    if platform.system().lower() == 'windows':
        for ext in ['.bat', '.exe', '.cmd']:
            tool_path = TOOLS_DIR / f"{tool_name}{ext}"
            if tool_path.exists():
                return tool_path
    
    if tool_name == "jadx":
        jadx_bin = TOOLS_DIR / "jadx" / "bin" / "jadx"
        if jadx_bin.exists():
            return jadx_bin
        jadx_bin = TOOLS_DIR / "jadx" / "bin" / "jadx.bat"
        if jadx_bin.exists():
            return jadx_bin
    
    return None

def run_cmd(cmd, cwd=None, timeout=300):
    actual_cmd = []
    for arg in cmd:
        if arg in ["apktool", "jadx", "aapt2", "zipalign", "apksigner"]:
            tool_path = get_tool_path(arg)
            if tool_path:
                actual_cmd.append(str(tool_path))
            else:
                actual_cmd.append(arg)
        else:
            actual_cmd.append(arg)
    
    print(f"[CMD] {' '.join(actual_cmd)}")
    proc = subprocess.run(actual_cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"명령 실패 (code {proc.returncode}): {proc.stderr}")
    return proc.stdout, proc.stderr

# ========== 시작 시 의존성 설치 ==========
install_dependencies()

# ========== API 구현 ==========
def get_job_dir(job_id):
    return BASE_DIR / job_id

def cleanup_job(job_id):
    job_dir = get_job_dir(job_id)
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)

def build_tree(dir_path, rel_path=""):
    result = []
    if not dir_path.exists():
        return result
    for item in sorted(dir_path.iterdir()):
        if item.name.startswith('.'):
            continue
        node = {
            "name": item.name,
            "path": str(item.relative_to(dir_path)) if rel_path else item.name,
            "type": "directory" if item.is_dir() else "file"
        }
        if item.is_dir():
            node["children"] = build_tree(item, node["path"])
        result.append(node)
    return result

def extract_old_package(manifest_path):
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'package="([^"]+)"', content)
            if match:
                return match.group(1)
    except:
        pass
    return None

def build_combined_tree(job_dir):
    """통합 트리 생성 (apktool + jadx)"""
    combined_tree = []
    decompile_dir = job_dir / "decompiled"
    java_dir = job_dir / "java"
    
    # apktool 결과
    if decompile_dir.exists():
        combined_tree.extend(build_tree(decompile_dir))
    
    # jadx Java 소스
    if java_dir.exists():
        sources_dir = java_dir / "sources"
        if sources_dir.exists() and any(sources_dir.iterdir()):
            java_node = {
                "name": "java_sources",
                "path": "java_sources",
                "type": "directory",
                "children": build_tree(sources_dir)
            }
            combined_tree.append(java_node)
        elif any(java_dir.iterdir()):
            java_node = {
                "name": "java_sources",
                "path": "java_sources",
                "type": "directory",
                "children": build_tree(java_dir)
            }
            combined_tree.append(java_node)
    
    return combined_tree

# ========== API 엔드포인트 ==========
@app.route('/api/upload', methods=['POST'])
def upload_apk():
    if 'file' not in request.files:
        return jsonify({"error": "파일 없음"}), 400
    
    file = request.files['file']
    if not file.filename.endswith(('.apk', '.xapk')):
        return jsonify({"error": "APK/XAPK 파일만 지원"}), 400

    job_id = str(uuid.uuid4())[:8]
    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    orig_path = job_dir / "original.apk"
    file.save(orig_path)

    if file.filename.endswith('.xapk'):
        with zipfile.ZipFile(orig_path, 'r') as zf:
            apk_list = [f for f in zf.namelist() if f.endswith('.apk')]
            if not apk_list:
                return jsonify({"error": "XAPK 내 APK 없음"}), 400
            base_apk = apk_list[0]
            with zf.open(base_apk) as src, open(job_dir / "base.apk", 'wb') as dst:
                dst.write(src.read())
            apk_path = job_dir / "base.apk"
    else:
        apk_path = orig_path

    # 1. apktool 디컴파일
    decompile_dir = job_dir / "decompiled"
    try:
        run_cmd(["apktool", "d", "-f", "-o", str(decompile_dir), str(apk_path)])
    except Exception as e:
        cleanup_job(job_id)
        return jsonify({"error": f"apktool 디컴파일 실패: {str(e)}"}), 500

    # 2. jadx Java 소스 추출
    java_dir = job_dir / "java"
    try:
        run_cmd([
            "jadx", "-d", str(java_dir),
            "--show-bad-code",
            "--no-res",
            "--threads-count", "2",
            str(apk_path)
        ], timeout=1800)
        print(f"[+] Java 디컴파일 완료: {java_dir}")
    except Exception as e:
        print(f"[WARN] jadx 실패: {e}")

    # 3. 통합 트리 생성
    combined_tree = build_combined_tree(job_dir)

    meta = {
        "job_id": job_id,
        "apk_path": str(apk_path),
        "decompile_dir": str(decompile_dir),
        "java_dir": str(java_dir) if java_dir.exists() else None,
        "original_name": file.filename,
    }
    with open(job_dir / "meta.json", 'w') as f:
        json.dump(meta, f)

    return jsonify({
        "job_id": job_id,
        "tree": combined_tree,
        "message": "디컴파일 완료"
    })

@app.route('/api/files/<job_id>', methods=['GET'])
def get_file_tree(job_id):
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return jsonify({"error": "작업 없음"}), 404
    
    combined_tree = build_combined_tree(job_dir)
    if not combined_tree:
        return jsonify({"error": "디컴파일된 파일이 없음"}), 404
    
    return jsonify({"tree": combined_tree})

@app.route('/api/file/<job_id>/<path:file_path>', methods=['GET'])
def get_file_content(job_id, file_path):
    job_dir = get_job_dir(job_id)
    
    # apktool 결과에서 먼저 찾기
    decompile_path = job_dir / "decompiled" / file_path
    if decompile_path.exists() and decompile_path.is_file():
        target = decompile_path
    else:
        # java_sources 경로 처리
        if file_path.startswith("java_sources/"):
            java_path = file_path.replace("java_sources/", "")
            target = job_dir / "java" / "sources" / java_path
            if not target.exists():
                target = job_dir / "java" / java_path
        else:
            target = job_dir / "decompiled" / file_path
    
    if not target.exists() or not target.is_file():
        abort(404, "파일 없음")
    
    try:
        with open(target, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return jsonify({"error": "바이너리 파일은 편집 불가"}), 400
    
    return content

@app.route('/api/file/<job_id>/<path:file_path>', methods=['PUT'])
def save_file_content(job_id, file_path):
    job_dir = get_job_dir(job_id)
    
    # 저장 경로 결정 (decompiled 내부만 저장 가능)
    if file_path.startswith("java_sources/"):
        return jsonify({"error": "Java 소스 파일은 읽기 전용"}), 403
    
    target = job_dir / "decompiled" / file_path
    if not target.exists() or not target.is_file():
        abort(404, "파일 없음")
    
    data = request.get_json()
    if 'content' not in data:
        return jsonify({"error": "content 필드 필요"}), 400
    
    try:
        with open(target, 'w', encoding='utf-8') as f:
            f.write(data['content'])
    except Exception as e:
        return jsonify({"error": f"저장 실패: {str(e)}"}), 500
    
    return jsonify({"message": "저장 완료"})

@app.route('/api/rebuild/<job_id>', methods=['POST'])
def rebuild_apk(job_id):
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return jsonify({"error": "작업 없음"}), 404
    
    data = request.get_json()
    new_package = data.get('new_package', '').strip()
    if not new_package:
        return jsonify({"error": "새 패키지명 필요"}), 400
    
    decompile_dir = job_dir / "decompiled"
    if not decompile_dir.exists():
        return jsonify({"error": "디컴파일 디렉토리 없음"}), 404

    manifest_path = decompile_dir / "AndroidManifest.xml"
    old_pkg = extract_old_package(manifest_path) if manifest_path.exists() else None
    
    if not old_pkg:
        return jsonify({"error": "기존 패키지명을 찾을 수 없음"}), 400

    print(f"[*] 패키지명 변경: {old_pkg} → {new_package}")

    # 1. AndroidManifest.xml 패키지명 변경
    if manifest_path.exists():
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = f.read()
        manifest = re.sub(r'package="[^"]*"', f'package="{new_package}"', manifest)
        # 내부 모든 패키지 참조도 변경
        manifest = manifest.replace(old_pkg, new_package)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(manifest)

    old_path = old_pkg.replace('.', '/')
    new_path = new_package.replace('.', '/')

    # 2. 모든 smali 디렉토리 처리
    smali_dirs = [d for d in decompile_dir.iterdir() if d.is_dir() and d.name.startswith("smali")]
    for smali_dir in smali_dirs:
        for smali_file in smali_dir.rglob("*.smali"):
            try:
                with open(smali_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 클래스 경로 치환
                content = content.replace(f'L{old_path}/', f'L{new_path}/')
                # R 클래스 참조 치환
                content = content.replace(f'L{old_pkg}/R$', f'L{new_package}/R$')
                # 일반 패키지명 치환
                content = content.replace(old_pkg, new_package)
                
                with open(smali_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                print(f"[WARN] smali 치환 실패 {smali_file}: {e}")

    # 3. 모든 XML 리소스 파일 처리
    res_dir = decompile_dir / "res"
    if res_dir.exists():
        for xml_file in res_dir.rglob("*.xml"):
            try:
                with open(xml_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace(old_pkg, new_package)
                with open(xml_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                print(f"[WARN] XML 치환 실패 {xml_file}: {e}")

    # 4. 리빌드
    repack_dir = job_dir / "repacked"
    repack_dir.mkdir(exist_ok=True)
    try:
        run_cmd(["apktool", "b", str(decompile_dir), "-o", str(repack_dir / "unsigned.apk")])
    except Exception as e:
        return jsonify({"error": f"리빌드 실패: {str(e)}"}), 500

    # 5. Zipalign
    aligned_apk = repack_dir / "aligned.apk"
    try:
        run_cmd(["zipalign", "-v", "-p", "4", str(repack_dir / "unsigned.apk"), str(aligned_apk)])
    except Exception as e:
        return jsonify({"error": f"zipalign 실패: {str(e)}"}), 500

    # 6. 서명
    signed_apk = repack_dir / "signed.apk"
    debug_keystore = TOOLS_DIR / "debug.keystore"
    try:
        if debug_keystore.exists():
            run_cmd([
                "apksigner", "sign",
                "--ks", str(debug_keystore),
                "--ks-pass", "pass:android",
                "--out", str(signed_apk),
                str(aligned_apk)
            ])
        else:
            run_cmd([
                "apksigner", "sign",
                "--debug-key",
                "--out", str(signed_apk),
                str(aligned_apk)
            ])
    except Exception as e:
        try:
            jarsigner = shutil.which("jarsigner")
            if jarsigner:
                run_cmd([
                    jarsigner, "-verbose", "-sigalg", "SHA1withRSA",
                    "-digestalg", "SHA1",
                    "-keystore", str(debug_keystore) if debug_keystore.exists() else "debug.keystore",
                    "-storepass", "android",
                    "-keypass", "android",
                    str(aligned_apk), "androiddebugkey"
                ])
                shutil.copy(aligned_apk, signed_apk)
            else:
                raise RuntimeError("jarsigner 없음")
        except Exception as e2:
            return jsonify({"error": f"서명 실패: {str(e2)}"}), 500

    # 7. 다운로드 준비
    download_dir = BASE_DIR / "downloads"
    download_dir.mkdir(exist_ok=True)
    final_apk = download_dir / f"{job_id}_signed.apk"
    shutil.copy(signed_apk, final_apk)

    return jsonify({
        "message": "리빌드 및 서명 완료",
        "download_url": f"/api/download/{job_id}"
    })

@app.route('/api/download/<job_id>', methods=['GET'])
def download_apk(job_id):
    download_dir = BASE_DIR / "downloads"
    target = download_dir / f"{job_id}_signed.apk"
    if not target.exists():
        abort(404, "APK 없음")
    return send_file(target, as_attachment=True, download_name=f"{job_id}_signed.apk")

@app.route('/api/cleanup/<job_id>', methods=['DELETE'])
def cleanup(job_id):
    cleanup_job(job_id)
    download_dir = BASE_DIR / "downloads"
    for f in download_dir.glob(f"{job_id}_*"):
        f.unlink()
    return jsonify({"message": "삭제 완료"})

if __name__ == '__main__':
    print("[*] APKWorkshop 서버 시작 (PORT 10000)")
    print(f"[*] 서버 디렉토리: {SERVER_DIR}")
    print(f"[*] 작업 디렉토리: {BASE_DIR}")
    print(f"[*] 도구 디렉토리: {TOOLS_DIR}")
    print("[*] http://localhost:10000 에서 접속 가능")
    app.run(host='0.0.0.0', port=10000, debug=False, threaded=True)
