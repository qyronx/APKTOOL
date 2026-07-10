# server.py - APKWorkshop NullByte (패키지명 변경 전용 - resources.arsc 완전 수정)
# 실행: python server.py (포트 10000)

import os
import sys
import platform
import subprocess
import shutil
import json
import uuid
import zipfile
import urllib.request
import tarfile
import re
import stat
import threading
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ========== 작업 상태 저장 ==========
job_status = {}  # job_id -> {"status": "processing"|"done"|"failed", "result": {}, "progress": 0}

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
    return False

def ensure_java():
    if is_java_installed():
        ver = get_java_version()
        print(f"[*] Java 발견 (버전 {ver})")
        if ver >= 11:
            return True
        else:
            print(f"[!] Java 버전이 낮음 (11+ 필요)")
    
    print("[*] Java 자동 설치 시도...")
    
    system = platform.system().lower()
    success = False
    
    if system == 'linux':
        success = install_java_linux()
    elif system == 'windows':
        success = install_java_windows()
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
        return jsonify({"error": "index.html 파일이 없습니다."}), 404

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
    return False

# ========== 자동 의존성 설치 ==========
def _install_zipalign():
    """zipalign 설치 (없을 경우)"""
    zipalign_path = TOOLS_DIR / "zipalign"
    if zipalign_path.exists():
        return zipalign_path
    
    system = platform.system().lower()
    is_linux = system == 'linux'
    is_windows = system == 'windows'
    
    try:
        if is_linux:
            urllib.request.urlretrieve(
                "https://dl.google.com/android/repository/build-tools_r34-linux.zip",
                TOOLS_DIR / "build-tools.zip"
            )
            with zipfile.ZipFile(TOOLS_DIR / "build-tools.zip", 'r') as zf:
                zf.extractall(TOOLS_DIR)
            (TOOLS_DIR / "build-tools.zip").unlink()
            
            for f in TOOLS_DIR.glob("**/zipalign"):
                if f.is_file():
                    shutil.move(str(f), str(zipalign_path))
                    zipalign_path.chmod(0o755)
                    return zipalign_path
                    
        elif is_windows:
            urllib.request.urlretrieve(
                "https://dl.google.com/android/repository/build-tools_r34-windows.zip",
                TOOLS_DIR / "build-tools.zip"
            )
            with zipfile.ZipFile(TOOLS_DIR / "build-tools.zip", 'r') as zf:
                zf.extractall(TOOLS_DIR)
            (TOOLS_DIR / "build-tools.zip").unlink()
            
            for f in TOOLS_DIR.glob("**/zipalign.exe"):
                if f.is_file():
                    shutil.move(str(f), str(TOOLS_DIR / "zipalign.exe"))
                    return TOOLS_DIR / "zipalign.exe"
    except Exception as e:
        print(f"[!] zipalign 설치 실패: {e}")
    
    return None

def install_dependencies():
    print("[*] 의존성 설치 시작...")
    print(f"[*] 서버 디렉토리: {SERVER_DIR}")
    print(f"[*] 도구 디렉토리: {TOOLS_DIR}")
    
    ensure_java()
    
    system = platform.system().lower()
    is_linux = system == 'linux'
    is_windows = system == 'windows'

    # ★★★ apktool 2.9.3 설치 (최신 버전) ★★★
    print("[*] apktool 2.9.3 설치 중...")
    try:
        for f in TOOLS_DIR.glob("apktool*"):
            if f.is_file():
                f.unlink()
        
        if is_linux:
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/linux/apktool",
                TOOLS_DIR / "apktool"
            )
            (TOOLS_DIR / "apktool").chmod(0o755)
            urllib.request.urlretrieve(
                "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar",
                TOOLS_DIR / "apktool.jar"
            )
        elif is_windows:
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/windows/apktool.bat",
                TOOLS_DIR / "apktool.bat"
            )
            urllib.request.urlretrieve(
                "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar",
                TOOLS_DIR / "apktool.jar"
            )
        print("[+] apktool 2.9.3 설치 완료")
    except Exception as e:
        print(f"[!] apktool 설치 실패: {e}")
    
    # zipalign 설치
    _install_zipalign()
    
    # 디버그 키스토어 생성
    debug_keystore = TOOLS_DIR / "debug.keystore"
    if not debug_keystore.exists():
        print("[*] 디버그 키스토어 생성 중...")
        keytool_path = shutil.which("keytool")
        if keytool_path:
            try:
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
                if debug_keystore.exists():
                    print("[+] 디버그 키스토어 생성 완료 (keytool)")
            except Exception as e:
                print(f"[!] keytool 실패: {e}")
        
        if not debug_keystore.exists():
            apksigner = shutil.which("apksigner")
            if apksigner:
                try:
                    dummy_apk = TOOLS_DIR / "dummy.apk"
                    with open(dummy_apk, 'wb') as f:
                        f.write(b'PK\x03\x04')
                    subprocess.run([
                        apksigner, "sign",
                        "--debug-key",
                        "--out", str(TOOLS_DIR / "dummy_signed.apk"),
                        str(dummy_apk)
                    ], check=False, timeout=10)
                    home_keystore = Path.home() / ".android" / "debug.keystore"
                    if home_keystore.exists():
                        shutil.copy(home_keystore, debug_keystore)
                        print(f"[+] 디버그 키스토어 복사 완료 (apksigner)")
                    if dummy_apk.exists():
                        dummy_apk.unlink()
                    if (TOOLS_DIR / "dummy_signed.apk").exists():
                        (TOOLS_DIR / "dummy_signed.apk").unlink()
                except Exception as e:
                    print(f"[!] apksigner 디버그 키 생성 실패: {e}")
        
        if debug_keystore.exists():
            print("[+] 디버그 키스토어 생성 완료")
        else:
            print("[!] 디버그 키스토어 생성 실패. 서명 없이 진행됩니다.")
    
    print("[+] 의존성 설치 완료")

# ========== 도구 경로 헬퍼 ==========
def get_tool_path(tool_name):
    if shutil.which(tool_name):
        return Path(shutil.which(tool_name))
    tool_path = TOOLS_DIR / tool_name
    if tool_path.exists():
        return tool_path
    return None

def run_cmd(cmd, cwd=None, timeout=7200):
    actual_cmd = []
    for arg in cmd:
        if arg in ["apktool", "jarsigner", "apksigner"]:
            tool_path = get_tool_path(arg)
            if tool_path:
                actual_cmd.append(str(tool_path))
            else:
                actual_cmd.append(arg)
        else:
            actual_cmd.append(arg)
    
    print(f"[CMD] {' '.join(actual_cmd)}")
    
    env = os.environ.copy()
    
    proc = subprocess.run(
        actual_cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env
    )
    
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
    if job_id in job_status:
        del job_status[job_id]

def extract_package_name(manifest_path):
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'package="([^"]+)"', content)
            if match:
                return match.group(1)
    except:
        pass
    return None

def replace_in_all_files(decompile_dir, old_pkg, new_package):
    """모든 파일에서 패키지명 치환 (병렬 처리)"""
    import concurrent.futures
    
    old_path = old_pkg.replace('.', '/')
    new_path = new_package.replace('.', '/')
    
    # 1. AndroidManifest.xml 먼저 처리
    manifest_path = decompile_dir / "AndroidManifest.xml"
    if manifest_path.exists():
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = f.read()
        manifest = re.sub(r'package="[^"]*"', f'package="{new_package}"', manifest)
        manifest = manifest.replace(old_pkg, new_package)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(manifest)
    
    # 2. smali 파일들 병렬 처리
    smali_dirs = [d for d in decompile_dir.iterdir() if d.is_dir() and d.name.startswith("smali")]
    
    def process_smali_file(smali_file):
        try:
            with open(smali_file, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace(f'L{old_path}/', f'L{new_path}/')
            content = content.replace(f'L{old_pkg}/R$', f'L{new_package}/R$')
            content = content.replace(old_pkg, new_package)
            with open(smali_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"[WARN] smali 치환 실패 {smali_file}: {e}")
            return False
    
    smali_files = []
    for smali_dir in smali_dirs:
        smali_files.extend(smali_dir.rglob("*.smali"))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        executor.map(process_smali_file, smali_files)
    
    # 3. XML 리소스 파일 병렬 처리
    res_dir = decompile_dir / "res"
    if res_dir.exists():
        xml_files = list(res_dir.rglob("*.xml"))
        
        def process_xml_file(xml_file):
            try:
                with open(xml_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace(old_pkg, new_package)
                with open(xml_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True
            except Exception as e:
                print(f"[WARN] XML 치환 실패 {xml_file}: {e}")
                return False
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            executor.map(process_xml_file, xml_files)

def update_apktool_yml(decompile_dir, old_pkg, new_package):
    """apktool.yml 업데이트 (YAML 구조 유지)"""
    yml_path = decompile_dir / "apktool.yml"
    if not yml_path.exists():
        return
    
    with open(yml_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # doNotCompress 처리
    if 'doNotCompress:' in content:
        if 'resources.arsc' not in content:
            # 기존 항목 뒤에 추가
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                new_lines.append(line)
                if line.strip() == 'doNotCompress:':
                    # 다음 줄부터 들여쓰기 확인
                    indent = ''
                    for char in line:
                        if char == ' ':
                            indent += ' '
                        else:
                            break
                    new_lines.append(f'{indent}  - resources.arsc')
            content = '\n'.join(new_lines)
    else:
        content += '\ndoNotCompress:\n  - resources.arsc\n'
    
    # renameManifestPackage 업데이트
    if 'renameManifestPackage:' in content:
        content = re.sub(
            r'renameManifestPackage:\s*.*',
            f'renameManifestPackage: {new_package}',
            content
        )
    else:
        content += f'\nrenameManifestPackage: {new_package}\n'
    
    with open(yml_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[+] apktool.yml 업데이트 완료")

def fix_resources_arsc(apk_path):
    """
    resources.arsc를 STORED (압축 해제) 방식으로 변환
    Android 11+에서 필수
    """
    if not apk_path.exists():
        return False
    
    try:
        temp_path = apk_path.with_suffix(".fixed.apk")
        
        with zipfile.ZipFile(apk_path, 'r') as zin:
            with zipfile.ZipFile(temp_path, 'w') as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    
                    if item.filename == "resources.arsc":
                        # STORED로 다시 쓰기 (압축 해제)
                        info = zipfile.ZipInfo(item.filename)
                        info.date_time = item.date_time
                        info.compress_type = zipfile.ZIP_STORED
                        info.external_attr = item.external_attr
                        info.create_system = item.create_system
                        zout.writestr(info, data)
                        print(f"[+] resources.arsc를 STORED로 변환 (압축 해제)")
                    else:
                        zout.writestr(item, data)
        
        # 원본을 수정된 파일로 교체
        shutil.move(temp_path, apk_path)
        return True
        
    except Exception as e:
        print(f"[!] resources.arsc 수정 실패: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False

# ========== 백그라운드 리빌드 작업 ==========
def rebuild_async(job_id, new_package, old_pkg, decompile_dir):
    """백그라운드에서 리빌드 실행 (resources.arsc 완전 수정)"""
    try:
        job_status[job_id] = {"status": "processing", "progress": 10}
        
        # 1. 패키지명 치환 (병렬)
        job_status[job_id]["progress"] = 20
        replace_in_all_files(decompile_dir, old_pkg, new_package)
        job_status[job_id]["progress"] = 35
        
        # 2. apktool.yml 업데이트
        update_apktool_yml(decompile_dir, old_pkg, new_package)
        job_status[job_id]["progress"] = 40
        
        # 3. apktool 리빌드
        repack_dir = decompile_dir.parent / "repacked"
        repack_dir.mkdir(exist_ok=True)
        
        job_status[job_id]["progress"] = 45
        
        env = os.environ.copy()
        env["_JAVA_OPTIONS"] = "-Xmx256m -Xms64m -XX:+UseSerialGC"
        
        apktool_path = get_tool_path("apktool")
        if not apktool_path:
            raise RuntimeError("apktool을 찾을 수 없음")
        
        unsigned_apk = repack_dir / "unsigned.apk"
        
        cmd = [
            str(apktool_path), "b",
            "--no-debug",
            str(decompile_dir),
            "-o", str(unsigned_apk)
        ]
        
        print(f"[CMD] {' '.join(cmd)}")
        print(f"[JVM] {env.get('_JAVA_OPTIONS', '')}")
        
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, env=env)
        if proc.returncode != 0:
            raise RuntimeError(f"apktool 리빌드 실패: {proc.stderr}")
        
        print("[+] apktool 리빌드 완료")
        job_status[job_id]["progress"] = 55
        
        # ★★★ 4. resources.arsc를 STORED로 변환 (핵심) ★★★
        print("[*] resources.arsc를 STORED로 변환 중...")
        if not fix_resources_arsc(unsigned_apk):
            print("[!] resources.arsc 변환 실패, 계속 진행")
        job_status[job_id]["progress"] = 65
        
        # ★★★ 5. zipalign 실행 (4바이트 정렬) ★★★
        aligned_apk = repack_dir / "aligned.apk"
        zipalign_path = get_tool_path("zipalign")
        
        if not zipalign_path:
            zipalign_path = _install_zipalign()
        
        if zipalign_path and zipalign_path.exists():
            print("[*] zipalign 실행 중...")
            cmd = [
                str(zipalign_path), "-f", "-v", "-p", "4",
                str(unsigned_apk), str(aligned_apk)
            ]
            print(f"[CMD] {' '.join(cmd)}")
            
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if proc.returncode == 0 and aligned_apk.exists():
                print("[+] zipalign 완료")
                if unsigned_apk.exists():
                    unsigned_apk.unlink()
            else:
                print(f"[WARN] zipalign 실패: {proc.stderr}")
                shutil.copy(unsigned_apk, aligned_apk)
        else:
            print("[!] zipalign 없음, unsigned 사용")
            shutil.copy(unsigned_apk, aligned_apk)
        
        job_status[job_id]["progress"] = 80
        
        # ★★★ 6. resources.arsc 검증 ★★★
        try:
            with zipfile.ZipFile(aligned_apk, 'r') as z:
                info = z.getinfo("resources.arsc")
                print(f"[*] resources.arsc compress_type: {info.compress_type}")
                if info.compress_type == 0:
                    print("[+] resources.arsc가 STORED(압축 해제) 상태입니다.")
                else:
                    print(f"[!] resources.arsc가 압축됨 (compress_type={info.compress_type})")
        except Exception as e:
            print(f"[!] resources.arsc 검증 실패: {e}")
        
        # 7. 서명 (v1+v2+v3)
        signed_apk = repack_dir / "signed.apk"
        signed = False
        
        apksigner = shutil.which("apksigner")
        if apksigner:
            try:
                env = os.environ.copy()
                env["_JAVA_OPTIONS"] = "-Xmx128m"
                
                cmd = [
                    apksigner, "sign",
                    "--debug-key",
                    "--v1-signing-enabled", "true",
                    "--v2-signing-enabled", "true",
                    "--v3-signing-enabled", "true",
                    "--out", str(signed_apk),
                    str(aligned_apk)
                ]
                print(f"[CMD] {' '.join(cmd)}")
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
                if proc.returncode == 0 and signed_apk.exists():
                    signed = True
                    print("[+] apksigner 서명 완료 (v1+v2+v3)")
                else:
                    print(f"[!] apksigner v1+v2+v3 서명 실패: {proc.stderr}")
                    cmd = [
                        apksigner, "sign",
                        "--debug-key",
                        "--v1-signing-enabled", "true",
                        "--v2-signing-enabled", "false",
                        "--v3-signing-enabled", "false",
                        "--out", str(signed_apk),
                        str(aligned_apk)
                    ]
                    print(f"[CMD] {' '.join(cmd)}")
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
                    if proc.returncode == 0 and signed_apk.exists():
                        signed = True
                        print("[+] apksigner 서명 완료 (v1 only)")
                    else:
                        print(f"[!] apksigner v1 서명도 실패: {proc.stderr}")
                        
            except Exception as e:
                print(f"[!] apksigner 서명 실패: {e}")
        
        if not signed:
            jarsigner = shutil.which("jarsigner")
            debug_keystore = TOOLS_DIR / "debug.keystore"
            if jarsigner and debug_keystore.exists():
                try:
                    env = os.environ.copy()
                    env["_JAVA_OPTIONS"] = "-Xmx128m"
                    cmd = [
                        jarsigner, "-verbose",
                        "-sigalg", "SHA1withRSA",
                        "-digestalg", "SHA1",
                        "-keystore", str(debug_keystore),
                        "-storepass", "android",
                        "-keypass", "android",
                        str(aligned_apk), "androiddebugkey"
                    ]
                    print(f"[CMD] {' '.join(cmd)}")
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
                    if proc.returncode == 0:
                        shutil.copy(aligned_apk, signed_apk)
                        signed = True
                        print("[+] jarsigner 서명 완료 (v1 only)")
                    else:
                        print(f"[!] jarsigner 서명 실패: {proc.stderr}")
                except Exception as e:
                    print(f"[!] jarsigner 서명 실패: {e}")
        
        if not signed:
            print("[!] 서명 도구 없음. 서명되지 않은 APK 생성")
            shutil.copy(aligned_apk, signed_apk)
        
        # 8. 다운로드 준비
        download_dir = BASE_DIR / "downloads"
        download_dir.mkdir(exist_ok=True)
        final_apk = download_dir / f"{job_id}_signed.apk"
        shutil.copy(signed_apk, final_apk)
        
        job_status[job_id]["progress"] = 100
        job_status[job_id]["status"] = "done"
        job_status[job_id]["result"] = {
            "message": f"리빌드 완료: {old_pkg} → {new_package}",
            "download_url": f"/api/download/{job_id}",
            "signed": signed
        }
        print(f"[+] 리빌드 완료: {job_id}")
        
    except Exception as e:
        job_status[job_id]["status"] = "failed"
        job_status[job_id]["result"] = {"error": str(e)}
        print(f"[!] 리빌드 실패 {job_id}: {e}")
        import traceback
        traceback.print_exc()

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

    decompile_dir = job_dir / "decompiled"
    try:
        run_cmd(["apktool", "d", "-f", "-o", str(decompile_dir), str(apk_path)], timeout=1800)
        print(f"[+] apktool 디코딩 완료: {decompile_dir}")
    except Exception as e:
        return jsonify({"error": f"apktool 디코딩 실패: {str(e)}"}), 500

    manifest_path = decompile_dir / "AndroidManifest.xml"
    old_pkg = extract_package_name(manifest_path)
    
    if not old_pkg:
        return jsonify({"error": "패키지명을 찾을 수 없음"}), 400

    meta = {
        "job_id": job_id,
        "original_package": old_pkg,
        "original_name": file.filename,
        "decompile_dir": str(decompile_dir),
    }
    with open(job_dir / "meta.json", 'w') as f:
        json.dump(meta, f)

    return jsonify({
        "job_id": job_id,
        "original_package": old_pkg,
        "message": f"디컴파일 완료. 원본 패키지명: {old_pkg}"
    })

@app.route('/api/rebuild/<job_id>', methods=['POST'])
def rebuild_apk(job_id):
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return jsonify({"error": "작업 없음"}), 404
    
    data = request.get_json()
    new_package = data.get('new_package', '').strip()
    if not new_package:
        return jsonify({"error": "새 패키지명 필요"}), 400
    
    meta_path = job_dir / "meta.json"
    if not meta_path.exists():
        return jsonify({"error": "메타데이터 없음. 먼저 APK를 업로드하세요."}), 400
    
    with open(meta_path, 'r') as f:
        meta = json.load(f)
    
    old_pkg = meta.get("original_package")
    if not old_pkg:
        return jsonify({"error": "원본 패키지명을 찾을 수 없음"}), 400
    
    decompile_dir = job_dir / "decompiled"
    if not decompile_dir.exists():
        return jsonify({"error": "디컴파일 디렉토리 없음"}), 404

    print(f"[*] 백그라운드 리빌드 시작: {job_id} ({old_pkg} → {new_package})")
    
    job_status[job_id] = {"status": "processing", "progress": 0, "result": {}}
    
    thread = threading.Thread(
        target=rebuild_async,
        args=(job_id, new_package, old_pkg, decompile_dir)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        "message": "리빌드 시작됨 (백그라운드 처리)",
        "job_id": job_id,
        "status_url": f"/api/status/{job_id}"
    })

@app.route('/api/status/<job_id>', methods=['GET'])
def get_status(job_id):
    if job_id not in job_status:
        return jsonify({"error": "작업 없음"}), 404
    
    status = job_status[job_id]
    return jsonify({
        "job_id": job_id,
        "status": status["status"],
        "progress": status.get("progress", 0),
        "result": status.get("result", {})
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
