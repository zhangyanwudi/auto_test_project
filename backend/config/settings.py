"""
Django settings for auto_test_project backend.
"""
import os
from pathlib import Path

from base_utils.network_utils import get_local_ip
from base_utils.config_base import load_page_config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

# 本机局域网 IP：启动时自动检测一次，作为全局唯一的 IP 来源。
# 后续所有与 IP 相关的地方（ALLOWED_HOSTS / CORS / FRONTEND_URL / 回调地址等）统一引用此变量。
LOCAL_IP = get_local_ip()

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0']
if LOCAL_IP:
    ALLOWED_HOSTS.append(LOCAL_IP)

INSTALLED_APPS = [
    'config.apps.ConfigConfig',  # 项目配置（含自定义 runserver，须位于 staticfiles 之前）
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'apps.users.apps.UsersConfig',  # 按功能分类：用户模块
    'apps.menu_management.apps.MenuManagementConfig',  # 菜单管理
    'apps.role_management.apps.RoleManagementConfig',  # 角色
    'apps.scheduled_task.apps.ScheduledTaskConfig',  # 定时任务
    'apps.ai_helper.apps.AiHelperConfig',  # AI助手
    'apps.operate_tool.apps.OperateToolConfig',  # 运营工具（配置比对统计）
    'apps.gp_logcat.apps.GpLogcatConfig',  # GP商业化日志
    'apps.mock_api.apps.MockApiConfig',  # Mock接口管理
    'apps.case_govern.apps.CaseGovernConfig',  # 用例管理
    'apps.db_table_note.apps.DbTableNoteConfig',  # 数据库表备注
    'apps.llm.apps.LlmConfig',  # 本地LLM（Ollama）
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

# MySQL 数据库配置（本地连接：用户 root，密码 123456）
# 可通过环境变量覆盖：DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
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
    {'NAME': 'django.contrib.login.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.login.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.login.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.login.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 日志：未配置时 root 默认为 WARNING，业务代码里 logger.info 不会出现在控制台
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
        # Django 默认会给 django 包设 propagate，显式指定避免与 root 重复或级别被盖住
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
        # 业务 API（含 apis.scheduled_task.views 等）
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
        'apps.llm': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'apps.case_govern': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# 允许前端开发服务器跨域
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

# Vue 前端主页面地址：默认用本机 IP，保证局域网其它机器也能访问（统一引用 LOCAL_IP）
FRONTEND_URL = os.environ.get('FRONTEND_URL', f'http://{LOCAL_IP}:5173' if LOCAL_IP else 'http://localhost:5173')

# 服务端 OCR：pytesseract 使用的 tesseract 可执行文件路径（可选）。
# 不设则自动从 PATH 及常见路径探测；若仍报「未检测到 Tesseract」，请安装后设置，例如：
#   export TESSERACT_CMD=/opt/homebrew/bin/tesseract   # Apple Silicon Homebrew
TESSERACT_CMD = (os.environ.get('TESSERACT_CMD') or '').strip() or None

# 统一敏感配置（config/page_config.json，不入库），OCR / SSO 等均从这里读取
_PAGE_CONFIG = load_page_config()

# 腾讯云通用 OCR（图片识别接口默认使用）：优先环境变量，其次 page_config.json
_OCR_CFG = _PAGE_CONFIG.get('tencent_cloud', {}).get('ocr', {})
if not isinstance(_OCR_CFG, dict):
    _OCR_CFG = {}
TENCENT_OCR_SECRET_ID = (os.environ.get('TENCENT_OCR_SECRET_ID') or '').strip() or _OCR_CFG.get('secret_id') or None
TENCENT_OCR_SECRET_KEY = (os.environ.get('TENCENT_OCR_SECRET_KEY') or '').strip() or _OCR_CFG.get('secret_key') or None

# 配置比对：本地 git 配置仓库根目录（其下为各 project_name 子目录，如 gp_blockblast）
# 默认与「项目仓库 auto_test_project」同级：…/ZnYan/hsabtest_config（BASE_DIR 为 backend，上溯两级到 ZnYan）
_GIT_CONFIG_ROOT_DEFAULT = (BASE_DIR.parent.parent / 'zt_serverinterfacetest/hsabtest_config').resolve()
GIT_CONFIG_ROOT = os.environ.get('GIT_CONFIG_ROOT') or str(_GIT_CONFIG_ROOT_DEFAULT)

# 配置比对：git pull 使用的 SSH 密钥路径（可选）；不设则自动检测 ssh-agent 或 ~/.ssh/id_ed25519
GIT_SSH_KEY = (os.environ.get('GIT_SSH_KEY') or '').strip() or None

# 配置比对：git pull 超时（秒），避免网络/鉴权异常拖死请求
GIT_CONFIG_PULL_TIMEOUT_SEC = int(os.environ.get('GIT_CONFIG_PULL_TIMEOUT_SEC', '45'))
# 同一仓库根目录两次 pull 的最小间隔（秒），减轻 /get_adwaynum_file 等接口重复阻塞
GIT_CONFIG_PULL_THROTTLE_SEC = int(os.environ.get('GIT_CONFIG_PULL_THROTTLE_SEC', '90'))

# AI助手：智能体网关配置
_AI_HELPER_CONFIG_PATH = BASE_DIR / 'config' / 'ai_helper_config.json'
AI_HELPER_CONFIG = {}
try:
    import json
    with open(_AI_HELPER_CONFIG_PATH, 'r', encoding='utf-8') as _f:
        AI_HELPER_CONFIG = json.load(_f)
except Exception:
    AI_HELPER_CONFIG = {
        'gateway_url': '',
        'api_key': '',
        'model': '',
        'max_tokens': 4096,
        'temperature': 0.7,
        'timeout_seconds': 60,
    }

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

# 请求体大小限制，gp_logcat 等日志上报接口可能发送较大的 JSON 数据
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB

# ── 本地 Ollama LLM 配置 ──────────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'deepseek-r1:1.5b')
# 可选视觉模型（需先 ollama pull），留空则使用 OCR 提取图片文字
OLLAMA_VISION_MODEL = (os.environ.get('OLLAMA_VISION_MODEL') or '').strip() or ''
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get('OLLAMA_TIMEOUT_SECONDS', '120'))
OLLAMA_NUM_CTX = int(os.environ.get('OLLAMA_NUM_CTX', '8192'))
OLLAMA_TEMPERATURE = float(os.environ.get('OLLAMA_TEMPERATURE', '0.7'))
OLLAMA_MAX_CONTEXT_MESSAGES = int(os.environ.get('OLLAMA_MAX_CONTEXT_MESSAGES', '50'))
OLLAMA_DEFAULT_SYSTEM_PROMPT = '你是一个有帮助的AI助手，请用中文回答用户的问题。'
