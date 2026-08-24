"""
Django settings for auto_test_project backend.
"""
import os
import socket
from pathlib import Path

from base_utils.config_base import load_page_config

BASE_DIR = Path(__file__).resolve().parent.parent


def get_local_ip():
    """
    自动获取本机局域网IP地址（非127.0.0.1）。
    部署到任意电脑时，自动适配该电脑的IP，无需手动修改。
    """
    try:
        # 方法1：通过UDP连接外部地址获取出口IP（最可靠）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("223.5.5.5", 53))  # 阿里云DNS，国内更稳定
        local_ip = s.getsockname()[0]
        s.close()
        if local_ip and not local_ip.startswith("127."):
            return local_ip
    except Exception:
        pass

    try:
        # 方法2：通过hostname解析
        hostname = socket.gethostname()
        _, _, ip_list = socket.gethostbyname_ex(hostname)
        for ip in ip_list:
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    try:
        # 方法3：Linux下获取所有IP
        import subprocess
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if result.returncode == 0:
            ips = result.stdout.strip().split()
            for ip in ips:
                if ip and not ip.startswith("127."):
                    return ip
    except Exception:
        pass

    return None


# ═══════════════════════════════════════════════════════════════
# 核心：自动获取当前电脑的局域网IP
# ═══════════════════════════════════════════════════════════════
LOCAL_IP = get_local_ip()
print(f"[Django] 自动检测到本机IP: {LOCAL_IP}")  # 启动时会在控制台打印

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

# ═══════════════════════════════════════════════════════════════
# ALLOWED_HOSTS：自动加入本机IP，无需手动修改
# ═══════════════════════════════════════════════════════════════
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0']
if LOCAL_IP:
    ALLOWED_HOSTS.append(LOCAL_IP)

INSTALLED_APPS = [
    'config.apps.ConfigConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'apps.users.apps.UsersConfig',
    'apps.menu_management.apps.MenuManagementConfig',
    'apps.role_management.apps.RoleManagementConfig',
    'apps.scheduled_task.apps.ScheduledTaskConfig',
    'apps.ai_helper.apps.AiHelperConfig',  # AI助手
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'auto_test_db'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', '123456'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apis': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'apps.scheduled_task': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# ═══════════════════════════════════════════════════════════════
# CORS：自动加入本机IP，前端可以用 http://本机IP:5173 访问
# ═══════════════════════════════════════════════════════════════
CORS_ALLOWED_ORIGINS = [
    'http://127.0.0.1:5173',
    'http://localhost:5173',
    'http://127.0.0.1:5174',
    'http://localhost:5174',
]
if LOCAL_IP:
    CORS_ALLOWED_ORIGINS.extend([
        f'http://{LOCAL_IP}:5173',
        f'http://{LOCAL_IP}:5174',
    ])

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

# ═══════════════════════════════════════════════════════════════
# FRONTEND_URL：自动使用本机IP，无需手动修改
# ═══════════════════════════════════════════════════════════════
# 优先级：环境变量 > 自动检测的IP > 默认localhost
if os.environ.get('FRONTEND_URL'):
    FRONTEND_URL = os.environ.get('FRONTEND_URL')
elif LOCAL_IP:
    FRONTEND_URL = f'http://{LOCAL_IP}:5173'
else:
    FRONTEND_URL = 'http://localhost:5173'

TESSERACT_CMD = (os.environ.get('TESSERACT_CMD') or '').strip() or None

# 统一敏感配置（config/page_config.json，不入库）
_PAGE_CONFIG = load_page_config()

# 腾讯云通用 OCR：优先环境变量，其次 page_config.json
_OCR_CFG = _PAGE_CONFIG.get('tencent_cloud', {}).get('ocr', {})
if not isinstance(_OCR_CFG, dict):
    _OCR_CFG = {}
TENCENT_OCR_SECRET_ID = (os.environ.get('TENCENT_OCR_SECRET_ID') or '').strip() or _OCR_CFG.get('secret_id') or None
TENCENT_OCR_SECRET_KEY = (os.environ.get('TENCENT_OCR_SECRET_KEY') or '').strip() or _OCR_CFG.get('secret_key') or None

_GIT_CONFIG_ROOT_DEFAULT = (BASE_DIR.parent.parent / 'zt_serverinterfacetest/hsabtest_config').resolve()
GIT_CONFIG_ROOT = os.environ.get('GIT_CONFIG_ROOT') or str(_GIT_CONFIG_ROOT_DEFAULT)

GIT_SSH_KEY = (os.environ.get('GIT_SSH_KEY') or '').strip() or None

GIT_CONFIG_PULL_TIMEOUT_SEC = int(os.environ.get('GIT_CONFIG_PULL_TIMEOUT_SEC', '45'))
GIT_CONFIG_PULL_THROTTLE_SEC = int(os.environ.get('GIT_CONFIG_PULL_THROTTLE_SEC', '90'))

# youxi123 统一 SSO 登录配置（ticket 验证），凭证在 config/page_config.json 的 youxi123_sso 分组
_YOUXI123_SSO_DEFAULTS = {
    'login_url': '',
    'verify_url': '',
    'secret_key': '',
    'callback_url': '',
}
_SSO_CFG = _PAGE_CONFIG.get('youxi123_sso', {})
if not isinstance(_SSO_CFG, dict):
    _SSO_CFG = {}
YOUXI123_SSO_CONFIG = {**_YOUXI123_SSO_DEFAULTS, **_SSO_CFG}
