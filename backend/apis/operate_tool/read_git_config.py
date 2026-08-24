import json
import logging
import os
import re
import subprocess
import threading
import time

from django.conf import settings

from base_utils.path_base import (
    check_dirs,
    exists,
    get_directory_file,
    get_folder_name,
    joint_path,
    rmtree_directory,
)
from base_utils.persist_base import PersistBase

logger = logging.getLogger(__name__)

_git_registry_lock = threading.Lock()
_git_pull_locks: dict[str, threading.Lock] = {}
_last_git_pull_ts: dict[str, float] = {}
_adwaynum_project_locks: dict[str, threading.Lock] = {}

# GP / iOS 与 get_gp_adwaynum_file、get_ios_adwaynum_file_v2 中 time_slot_mapping 一致
_GP_ADWAYNUM_SLOT_MAP = {
    0: None,
    1: ["7day"],
    2: ["31day"],
    3: ["31day_later"],
}
_IOS_ADWAYNUM_SLOT_MAP = {
    0: None,
    1: ["[0,7)天", "0~7"],
    2: ["[7,31)天", "7~31"],
    3: ["[31，+∞)天", "31+"],
}

_COUNTRY_CODE_CN_MAP = {
    "US": "美国",
    "AU": "澳大利亚",
    "CA": "加拿大",
    "GB": "英国",
    "JP": "日本",
    "NZ": "新西兰",
    "AT": "奥地利",
    "BE": "比利时",
    "BG": "保加利亚",
    "CH": "瑞士",
    "CY": "塞浦路斯",
    "CZ": "捷克",
    "DE": "德国",
    "DK": "丹麦",
    "EE": "爱沙尼亚",
    "ES": "西班牙",
    "FI": "芬兰",
    "FR": "法国",
    "GR": "希腊",
    "CN": "中国",
    "HR": "克罗地亚",
    "HU": "匈牙利",
    "IE": "爱尔兰",
    "IS": "冰岛",
    "IT": "意大利",
    "LI": "列支敦士登",
    "LT": "立陶宛",
    "LU": "卢森堡",
    "LV": "拉脱维亚",
    "MT": "马耳他",
    "NL": "荷兰",
    "NO": "挪威",
    "PL": "波兰",
    "PT": "葡萄牙",
    "RO": "罗马尼亚",
    "SE": "瑞典",
    "SI": "斯洛文尼亚",
    "SK": "斯洛伐克",
    "BN": "文莱",
    "BT": "不丹",
    "KH": "柬埔寨",
    "KP": "朝鲜",
    "LA": "老挝",
    "LK": "斯里兰卡",
    "MM": "缅甸",
    "MN": "蒙古",
    "MV": "马尔代夫",
    "NP": "尼泊尔",
    "RU": "俄罗斯",
    "SG": "新加坡",
    "TL": "东帝汶",
    "VN": "越南",
    "BL": "圣巴泰勒米岛",
    "BO": "玻利维亚",
    "BZ": "伯利兹",
    "CL": "智利",
    "CR": "哥斯达黎加",
    "CU": "古巴",
    "DO": "多米尼加共和国",
    "EC": "厄瓜多尔",
    "GF": "法属圭亚那",
    "GP": "瓜德罗普",
    "GT": "危地马拉",
    "GY": "圭亚那",
    "HN": "洪都拉斯",
    "HT": "海地",
    "MF": "法属圣马丁",
    "MQ": "马提尼克岛",
    "NI": "尼加拉瓜",
    "PA": "巴拿马",
    "PE": "秘鲁",
    "PR": "波多黎各",
    "PY": "巴拉圭",
    "SR": "苏里南",
    "SV": "萨尔瓦多",
    "UY": "乌拉圭",
    "VE": "委内瑞拉",
    "DZ": "阿尔及利亚",
    "EG": "埃及",
    "KZ": "哈萨克斯坦",
    "BD": "孟加拉国",
    "IN": "印度",
    "ID": "印度",
    "TR": "土耳其",
    "RS": "塞尔维亚",
    "PK": "巴基斯坦",
    "GE": "格鲁吉亚",
    "TH": "泰国",
    "AR": "阿根廷",
    "PH": "菲律宾",
    "MY": "马来西亚",
    "BR": "巴西",
    "CO": "哥伦比亚",
    "MX": "墨西哥",
    "ZA": "南非",
}

def _project_adwaynum_lock(project_name: str) -> threading.Lock:
    with _git_registry_lock:
        if project_name not in _adwaynum_project_locks:
            _adwaynum_project_locks[project_name] = threading.Lock()
        return _adwaynum_project_locks[project_name]


def _adwaynum_official_cache_dir():
    d = joint_path(settings.BASE_DIR, 'data', 'adwaynum_file_cache')
    check_dirs(d)
    return d


def _adwaynum_official_cache_path(project_name: str) -> str:
    safe = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', project_name)
    return joint_path(_adwaynum_official_cache_dir(), f'{safe}_adwaynum_slots.json')


def _invalidate_adwaynum_slot_cache(project_name: str):
    """删除单个项目的方案列表正式磁盘缓存。"""
    p = _adwaynum_official_cache_path(project_name)
    if exists(p) and os.path.isfile(p):
        try:
            os.remove(p)
        except OSError as exc:
            logger.warning('remove adwaynum slot cache %s: %s', p, exc)


def _invalidate_all_adwaynum_slot_caches():
    """git 仓库有更新时清空各项目方案列表正式缓存，避免读到过期列表。"""
    d = _adwaynum_official_cache_dir()
    if not exists(d):
        return
    for name in os.listdir(d):
        if not name.endswith('_adwaynum_slots.json'):
            continue
        p = joint_path(d, name)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError as exc:
                logger.warning('remove adwaynum slot cache %s: %s', p, exc)


def _rebuild_adwaynum_file_cache_inner(project_name: str, *, force_git_pull: bool = False):
    """全量 recursion 扫描并写入正式磁盘缓存；出错时返回带 error 的 dict。"""
    reader = ReadGitConfig(project_name)
    if force_git_pull:
        reader._update_git_config(force=True)
        if reader.cache_data.contain(project_name):
            reader.cache_data.remove(project_name)
    if project_name.startswith('ios_'):
        slots = reader._sync_build_official_slots_ios_inner()
    else:
        slots = reader._sync_build_official_slots_gp_inner()
    if isinstance(slots, dict) and slots.get('error'):
        return slots
    reader._atomic_write_official_slots(slots)
    return slots


def sync_rebuild_adwaynum_file_cache(project_name: str):
    """同步重建方案列表磁盘缓存（阻塞至写完正式文件）；手动同步时强制 git pull。"""
    lock = _project_adwaynum_lock(project_name)
    with lock:
        result = _rebuild_adwaynum_file_cache_inner(project_name, force_git_pull=True)
        if isinstance(result, dict) and result.get('error'):
            raise ValueError(result['error'])


def async_rebuild_adwaynum_file_cache(project_name: str):
    """
    git pull 检测到更新后异步执行：对 project_name 全量 recursion 扫描，写入临时文件再替换正式缓存。
    与请求内同步重建共用同一套构建逻辑与项目级锁。
    """
    def _run():
        lock = _project_adwaynum_lock(project_name)
        with lock:
            try:
                result = _rebuild_adwaynum_file_cache_inner(project_name)
                if isinstance(result, dict) and result.get('error'):
                    logger.error('adwaynum cache async rebuild %s: %s', project_name, result['error'])
            except Exception:
                logger.exception('async_rebuild_adwaynum_file_cache failed: %s', project_name)

    threading.Thread(
        target=_run,
        name=f'adwaynum-cache-{project_name}',
        daemon=True,
    ).start()


def _git_pull_lock_for_root(git_root: str) -> threading.Lock:
    with _git_registry_lock:
        if git_root not in _git_pull_locks:
            _git_pull_locks[git_root] = threading.Lock()
        return _git_pull_locks[git_root]


class ReadGitConfig:
    def __init__(self, project_name, git_dir=None):
        # 定义变量
        self.project_name = project_name
        # 配置仓库根目录：优先入参，否则 settings.GIT_CONFIG_ROOT（默认 …/ZnYan/hsabtest_config）
        self.git_dir = (git_dir or getattr(settings, 'GIT_CONFIG_ROOT', None) or '').strip()
        self.project_dir = joint_path(self.git_dir, f'{self.project_name}')
        # 定义文件路径
        self.block_7day_files = []
        self.block_31day_files = []
        self.block_31day_later_files = []
        self.block_files = []
        # 目录与文件分隔符
        self.split_label="--"
        # 获取目录数
        self.dir_count=500
        # 加载缓存（目录与原先 GitConfigCache 一致）
        _cache_dir = joint_path(settings.BASE_DIR, 'data', 'git_config_cache')
        self.cache_data = PersistBase(file_name='git_cache_data', persist_dir=_cache_dir)
        # 最近一次 get_*_adwaynum_file 是否命中磁盘正式缓存（供 API 返回给前端）
        self._last_adwaynum_cache_meta = {'from_official_file': None}

    def _read_json(self, file_path):
        """读取方案json"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.loads(file.read())

    @staticmethod
    def _resolve_ssh_auth_sock() -> str:
        """动态查找可用的 ssh-agent socket；找不到返回空字符串。"""
        import glob as _glob

        candidates: list[str] = []
        # macOS: launchd socket
        candidates.extend(sorted(_glob.glob('/private/tmp/com.apple.launchd.*/Listeners')))
        # Linux: 标准 ssh-agent socket
        candidates.extend(sorted(_glob.glob('/tmp/ssh-*/agent.*')))
        # 也加入环境变量中指定的 socket
        env_sock = os.environ.get('SSH_AUTH_SOCK', '')
        if env_sock and os.path.exists(env_sock) and env_sock not in candidates:
            candidates.insert(0, env_sock)

        logger.info('【git更新】候选 SSH_AUTH_SOCK (%d 个): %s', len(candidates), candidates)

        for sock_path in candidates:
            if not os.path.exists(sock_path):
                logger.info('【git更新】跳过不存在: %s', sock_path)
                continue
            # 直接用 ssh-add -l 验证是否有密钥（使用完整环境而非最小环境）
            try:
                test_env = os.environ.copy()
                test_env['SSH_AUTH_SOCK'] = sock_path
                result = subprocess.run(
                    ['ssh-add', '-l'],
                    capture_output=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=5,
                    env=test_env,
                    check=False,
                )
                if result.returncode == 0 and (result.stdout or '').strip():
                    logger.info('【git更新】通过 ssh-add -l 验证: %s', sock_path)
                    return sock_path
                else:
                    logger.info(
                        '【git更新】socket %s ssh-add -l 失败 (rc=%d, stdout=%r, stderr=%r)',
                        sock_path, result.returncode,
                        (result.stdout or '').strip()[:120],
                        (result.stderr or '').strip()[:120],
                    )
            except Exception as exc:
                logger.info('【git更新】socket %s ssh-add -l 异常: %s', sock_path, exc)

        return ''

    @staticmethod
    def _resolve_ssh_key() -> str:
        """按优先级解析 SSH 私钥路径，找不到返回空字符串。

        优先级：GIT_SSH_KEY 配置 > 无 passphrase 的 deploy key > 其他密钥
        """
        configured = getattr(settings, 'GIT_SSH_KEY', None)
        if configured and os.path.isfile(configured):
            return configured
        # 优先选择无 passphrase 的 deploy key（可在非终端环境中使用）
        deploy_candidates = (
            os.path.expanduser('~/.ssh/id_ed25519_deploy'),
            os.path.expanduser('~/.ssh/id_rsa_deploy'),
        )
        for candidate in deploy_candidates:
            if os.path.isfile(candidate):
                return candidate
        # 回退到其他密钥（可能有 passphrase，依赖 ssh-agent 或 Keychain）
        for name in ('id_ed25519', 'id_rsa', 'id_ecdsa'):
            candidate = os.path.expanduser(f'~/.ssh/{name}')
            if os.path.isfile(candidate) and candidate not in deploy_candidates:
                return candidate
        return ''

    def _update_git_config(self, force: bool = False) -> bool:
        """在配置仓库根目录执行 git pull；带超时、节流与同根目录互斥。返回是否判定为拉取到内容更新。"""
        git_dir = (self.git_dir or '').strip()
        logger.info(f"【git更新】更新git 目录：{git_dir}")
        if not git_dir or not exists(git_dir) or not os.path.isdir(git_dir):
            return False

        root_key = os.path.normpath(git_dir)
        throttle = max(0, int(getattr(settings, 'GIT_CONFIG_PULL_THROTTLE_SEC', 90)))
        timeout = max(5, int(getattr(settings, 'GIT_CONFIG_PULL_TIMEOUT_SEC', 45)))
        lock = _git_pull_lock_for_root(root_key)

        # 构造子进程环境变量：优先利用已解锁的 ssh-agent；兜底显式指定密钥文件
        subprocess_env = os.environ.copy()
        if not subprocess_env.get('GIT_SSH_COMMAND'):
            ssh_auth_sock = subprocess_env.get('SSH_AUTH_SOCK', '')
            if not ssh_auth_sock:
                # Django 可能未继承终端中的 SSH_AUTH_SOCK，尝试动态查找
                found_sock = ReadGitConfig._resolve_ssh_auth_sock()
                if found_sock:
                    subprocess_env['SSH_AUTH_SOCK'] = found_sock
                    ssh_auth_sock = found_sock
                    logger.info('【git更新】动态找到 SSH_AUTH_SOCK: %s', found_sock)

            ssh_key = ReadGitConfig._resolve_ssh_key()
            if ssh_auth_sock:
                # ssh-agent 可用，优先使用 agent（密钥已解锁无需 passphrase）
                subprocess_env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=no'
                logger.info(
                    '【git更新】使用 ssh-agent 认证, SSH_AUTH_SOCK=%s',
                    ssh_auth_sock,
                )
            elif ssh_key:
                # 无 agent 时显式指定密钥（需 macOS Keychain 或免密密钥）
                subprocess_env['GIT_SSH_COMMAND'] = (
                    f'ssh -i {ssh_key} -o StrictHostKeyChecking=no -o IdentitiesOnly=yes'
                )
                logger.info('【git更新】使用显式密钥 %s (无 ssh-agent)', ssh_key)
            else:
                logger.warning('【git更新】未找到 SSH 密钥且 SSH_AUTH_SOCK 不可用，git pull 可能失败')

        with lock:
            now = time.time()
            last = _last_git_pull_ts.get(root_key)
            if not force and last is not None and throttle and (now - last) < throttle:
                return False

            try:
                result = subprocess.run(
                    ['git', 'pull', 'origin', 'master'],
                    capture_output=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=git_dir,
                    check=False,
                    timeout=timeout,
                    env=subprocess_env,
                )
            except subprocess.TimeoutExpired:
                logger.info('【git更新】git pull 超时 (>%ss)，跳过: %s', timeout, git_dir)
                _last_git_pull_ts[root_key] = time.time()
                return False
            except OSError as e:
                logger.info('【git更新】git pull 无法执行: %s (%s)', git_dir, e)
                _last_git_pull_ts[root_key] = time.time()
                return False
            except Exception as e:
                logger.info(f"【git更新】git pull 异常：{e}")
                _last_git_pull_ts[root_key] = time.time()
                return False

            output = (result.stdout or '') + (result.stderr or '')
            logger.info(f"【git更新】输出执行结果：{output}")

            has_updates = self._check_git_updates(output)
            logger.info(f"【git更新】git 检查文件，结果{has_updates}")
            if has_updates:
                logger.info("【git更新】git 更新成功")
                pdir = self.cache_data.persist_dir
                rmtree_directory(pdir)
                check_dirs(pdir)
                self.cache_data = PersistBase(file_name='git_cache_data', persist_dir=pdir)
                _invalidate_all_adwaynum_slot_caches()
                async_rebuild_adwaynum_file_cache(self.project_name)

            _last_git_pull_ts[root_key] = time.time()
            logger.info(f"【git更新】更新git 操作完成！")
            return bool(has_updates)

    def _check_git_updates(self, output: str) -> bool:
        """
        检查 git pull 输出，判断是否有实际文件更新
        """
        # 有更新的典型特征
        update_patterns = [
            r'Updating\s+[\da-f]+\.\.[\da-f]+',  # Updating abc123..def456
            r'Fast-forward',  # Fast-forward
            r'Merge made by',  # 合并提交
            r'file changed',  # X files changed
            r'insertion',  # 有插入
            r'deletion',  # 有删除
            r'create mode',  # 新建文件
            r'delete mode',  # 删除文件
            r'rename',  # 重命名
        ]

        # 无更新的典型特征
        no_update_patterns = [
            r'Already up to date',  # 已是最新
            r'Already up-to-date',  # 变体
            r'Everything up-to-date',  # 全部最新
        ]

        output_lower = output.lower()

        # 先检查是否明确无更新
        for pattern in no_update_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return False

        # 再检查是否有更新迹象
        for pattern in update_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True

        # 如果命令成功执行(返回码0)但输出不明确，默认无更新
        # 如果返回码非0，可能是错误，也视为无有效更新
        return False


    def get_business_v(self, len_size=None):
        """获取期数"""
        self._update_git_config()

        business_v_list_dir = get_directory_file(
            self.project_dir,
            folder_only=True,
            exclude_names=['多聚合'],
            exclude_exact=True,
            filter_dot_prefix=False,
        )
        business_v_list_dir = sorted(business_v_list_dir, key=self._custom_sort, reverse=True)

        # 过滤非重要的期数
        filtered_list = [item for item in business_v_list_dir if not item.startswith("test")]

        if not len_size:
            return filtered_list

        # 定义正则：匹配纯数字，或纯数字后跟 -数字 或 _数字 的形式
        # 例如: '3300', '135-2', '91_2_config' 中的 '91_2' 部分，但这里我们检查整个字符串是否符合模式
        numeric_pattern = re.compile(r'^\d+([\-_]\d+)*$')

        result = []
        numeric_count = 0

        for item in filtered_list:
            # 检查是否是纯数字格式（包含 - 或 _ 连接的）
            if numeric_pattern.match(item):
                # 是数字格式，应用长度限制
                if numeric_count < len_size:
                    result.append(item)
                    numeric_count += 1
                # 超过限制则跳过
            else:
                # 不是数字格式（如 'xiaomi_pre', 'thelast_兜底' 等），直接保留
                result.append(item)

        return result

    def _custom_sort(self, version):
        """自定义期数排序"""
        # 使用正则表达式提取版本号中的数字部分
        match = re.search(r'\d+', version)
        if match:
            number = int(match.group())  # 提取数字部分
        else:
            number = 0
        return (len(str(number)), version)  # 先按长度，再按数字排序


    def _get_xiugai_adwaynum_file(self, time_slot_dir, xiugai_dir_names):
        """获取xiugai目录下的方案"""
        adwaynum_file = []
        for xiugai_dir_name in xiugai_dir_names:
            xiugai_dir = joint_path(time_slot_dir, xiugai_dir_name)
            # 获取xiugai目录下的文件且拼接——xiugai
            xiugai_adwaynum_file = [
                get_folder_name(file_name, is_extension=False) + f'-{xiugai_dir_name}'
                for file_name in get_directory_file(xiugai_dir, file_type=['.json'], filter_dot_prefix=False)
            ]
            adwaynum_file.extend(xiugai_adwaynum_file)
        return adwaynum_file


    def _dict_sorted(self, data_dict,sort_status=False):
        """对字典排序"""
        return dict(sorted(data_dict.items(),reverse=sort_status))

    def sort_json_by_keys_by_v1(self,json_data, indent=2):
        """
        对 JSON 字符串的键按字母顺序排序，返回排序后的 JSON 字符串。

        参数:
            json_str: 原始 JSON 字符串
            indent: 格式化缩进空格数，默认 2

        返回:
            排序后的 JSON 字符串
        """
        sorted_data = self.sort_dict_by_v1(json_data)
        return json.dumps(sorted_data, ensure_ascii=False, indent=indent)

    def sort_dict_by_v1(self,obj):
        """
        递归地对字典的键按字母顺序排序。
        列表中的字典也会递归排序。
        含 channel 的对象列表统一倒序：源数据常把公共配置放在末尾，
        倒序后左右节点按索引比对时公共项能对齐；不再按 JSON 内容排序，
        避免因元素内容不同排出不同顺序导致错位。
        """
        if isinstance(obj, dict):
            return {k: self.sort_dict_by_v1(v) for k, v in sorted(obj.items())}
        elif isinstance(obj, list):
            # 先递归处理每个元素（排序内部 dict key）
            processed = [self.sort_dict_by_v1(item) for item in obj]
            # 广告位 channel 列表统一倒序，保证不同节点（如 extra_01/extra_02）同一规则
            if processed and all(isinstance(x, dict) and 'channel' in x for x in processed):
                processed.reverse()
            return processed
        else:
            return obj

    def get_gp_adwaynum_json_v4(self, business_v, adwaynum_name, time_slot):
        """
        获取adwaynum_json
        20251003
        :param business_v:            期数    例：78_1
        :param adwaynum:            方案号     例：101-7day-12131
        :param time_slot:           时间段  1：代表0-7  2：代表7-31  3：31+    0:不区分
        :return:
        """
        try:
            business_dir = joint_path(self.project_dir, f"{business_v}")
            adwaynum_path = joint_path(business_dir, adwaynum_name.replace(self.split_label, '/') + ".json")

            self._update_git_config()

            if not exists(adwaynum_path):
                return {'error': '没有方案'}

            if str(self.project_name).endswith("_orth") or str(self.project_name).endswith("_rn") or str(self.project_name).endswith("_me")or str(self.project_name).endswith("_ml"):
                # AB平台
                name=adwaynum_name.rsplit("--", 1)[1]
                if name.startswith("me"):
                    # 互斥
                    print("互斥")
                    result=self._dict_sorted(self._get_gp_huci_json(adwaynum_path), sort_status=False)
                else:
                    print("正交")
                    result = self._dict_sorted(self._get_gp_json_by_ab_v3(adwaynum_path), sort_status=False)
            else:
                print("原生")
                # 原生
                result = self._dict_sorted(self._get_gp_json(adwaynum_path), sort_status=True)
            return result

        except Exception as e:
            return {"error": f"json配置异常{e}"}

    def _get_gp_json(self,adwaynum_path):
        """获取json文件"""
        adwaynum_json_map={}
        # 层级不一样，外层有的是list，有的是dict
        adwaynum_list = self._read_json(adwaynum_path)
        if isinstance(adwaynum_list, list):
            for adwaynum_json in adwaynum_list:
                country_list = adwaynum_json.get("country_list", [])
                country_list.sort(reverse=True)
                # 判断国家列表不为空时，取第一个国家
                if country_list:
                    country = self._country_cn_mapping(country_list[0],len(country_list))
                    ad_info = adwaynum_json.get("ad_info", {})
                    ad_info["country_list"] = country_list
                    self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                country_key=country,
                                                add_data=self._dict_sorted(ad_info))
            # 没有返最后一个
            return self._dict_sorted(self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                    country_key="其它",
                                                    add_data=self._dict_sorted(adwaynum_list[-1].get("ad_info", {}))), sort_status=True)
        elif isinstance(adwaynum_list, dict):
            adwaynum_json = adwaynum_list
            for key, json_value in adwaynum_json.items():
                if isinstance(json_value, dict):
                    country_list = json_value.get("list", [])
                    country_list.sort(reverse=True)
                    # 判断国家列表不为空时，取第一个国家
                    if country_list:
                        json_value["list"] = country_list
                        country = self._country_cn_mapping(country_list[0],len(country_list))
                        self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                    country_key=country,
                                                    add_data=self._dict_sorted(json_value))
            # 返回兜底配置
            default_json = adwaynum_json.get("default", {})
            # 处理有的配置没有default节点情况
            if not default_json:
                return self._dict_sorted(self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                country_key="其它",
                                                add_data= self._dict_sorted(adwaynum_json)), sort_status=True)
            return self._dict_sorted(self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                country_key="其它",
                                                add_data= self._dict_sorted(default_json)), sort_status=True)

    def _get_ios_json(self,adwaynum_path):
        """获取json文件"""
        adwaynum_json_map={}
        # 层级不一样，外层有的是list，有的是dict
        adwaynum_list = self._read_json(adwaynum_path)
        if isinstance(adwaynum_list, list):
            for adwaynum_json in adwaynum_list:
                country_list = adwaynum_json.get("country_list", [])
                if country_list:
                    country = self._country_cn_mapping(country_list[0],len(country_list))
                    ad_info = adwaynum_json.get("ad_info", {})
                    ad_info["country_list"] = country_list
                    self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                country_key=country,
                                                add_data=self._dict_sorted(ad_info))

            # 没有返最后一个
            return self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                    country_key="其它",
                                                    add_data=self._dict_sorted(adwaynum_list[-1].get("ad_info", {})))
        elif isinstance(adwaynum_list, dict):
            adwaynum_json = adwaynum_list
            for key, json_value in adwaynum_json.items():
                if isinstance(json_value, dict):
                    country_list = json_value.get("list", [])
                    country_list.sort(reverse=True)
                    if country_list:
                        json_value["list"] = country_list
                        country = self._country_cn_mapping(country_list[0],len(country_list))
                        self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                    country_key=country,
                                                    add_data=self._dict_sorted(json_value))

            # 返回兜底配置
            default_json = adwaynum_json.get("default", {})
            # 处理有的配置没有default节点情况
            if not default_json:
                self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                            country_key="其它",
                                            add_data= self._dict_sorted(adwaynum_json))
                return adwaynum_json_map
            self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                        country_key="其它",
                                        add_data=self._dict_sorted(default_json))
            return adwaynum_json_map

    def _get_ios_json_v2(self, adwaynum_path):
        """获取ios json文件"""
        adwaynum_json_map = {}
        json_data = self._read_json(adwaynum_path)
        if isinstance(json_data, dict):
            install_day_filters = json_data.get("install_day_filters", [])
            for _, install_day_filter in enumerate(install_day_filters):
                # 处理有国家配置
                country_filters = install_day_filter.get("country_filters", [])
                for country_index, country_filter in enumerate(country_filters):
                    # 按每个国家生成数据
                    key_name="_".join(["install_day",str(install_day_filter.get("install_day",-1)),str(f"国家-{country_index+1}")])
                    sort_json = self.sort_json_by_keys_by_v1(country_filter)
                    adwaynum_json_map.setdefault(key_name, json.loads(sort_json))
                    continue
                # 只处理兜底数据
                default_data=install_day_filter.get("default_data",{})
                sort_json=self.sort_json_by_keys_by_v1(default_data)
                key_name = "_".join(
                    ["install_day", str(install_day_filter.get("install_day", -1)), "其他"])
                adwaynum_json_map.setdefault(key_name, json.loads(sort_json))
        else:
            # 非字典走此逻辑
            for _,ad_info in enumerate(json_data):
                self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                            country_key="其它",
                                            add_data=self._dict_sorted(ad_info))

        logger.info(f"测试：{adwaynum_json_map}")
        return adwaynum_json_map

    def _add_adwaynum_json_map(self,adwaynum_json_map,country_key,add_data):
        """添加方案文件"""
        # 判断添加的国家key是否存在
        if country_key in adwaynum_json_map.keys():
            adwaynum_json_map["配置国家有重复项，请检查"]= {}
            return adwaynum_json_map
        adwaynum_json_map[country_key]=add_data
        return adwaynum_json_map

    def _country_cn_mapping(self,country,country_len=0):
        """国家中英对应关系"""
        # 处理GP方块
        if self.project_name in ["gp_blockblast","gp_blockblast_rn"]:
            if country in ["ID","TH","MY","PH","TR","KZ","PK","MX","BR","AR","CO","EG","ZA"] and country_len==13:
                return "低-13"
            elif country in ["DZ","GE","BD","RS","IN"] and country_len==5:
                return "低-5"
            elif country in ["CA","AU"] and country_len==2:
                return "加澳"
            elif country in ["DE","GB","FR","IT","ES","CH","SE","NL"] and country_len==8:
                return "欧洲地区"
            elif country in ["JP","KR","CN"] and country_len==3:
                return "日韩台"

        return _COUNTRY_CODE_CN_MAP.get(country, country)



    def _get_path_dir(self,path,dir_name=""):
        """
        获取路径下拼接目录的文件
        """
        file_result=[]
        while True:
            # 获取当路径下的目录
            next_dir_names = get_directory_file(path, folder_only=True, filter_dot_prefix=False)
            for next_dir_name in next_dir_names:
                # 拼接下层目录
                new_dir_name=dir_name+next_dir_name+self.split_label
                next_path=joint_path(path,next_dir_name)
                next_file_result=self._get_path_dir(next_path,new_dir_name)
                file_result.extend(next_file_result)
            # 判断是否有文件
            files = get_directory_file(path, include_names=['.'], filter_dot_prefix=False)
            # 先对文件排序
            files.sort(reverse=True)
            if files:
                for file in files:
                    # 将文件与目录结合
                    file_result.append(dir_name+get_folder_name(file,is_extension=False))
                return file_result
            return file_result

    def get_ios_adwaynum_file_v2(self, time_slot,business_v=None):
        """
        获取IOS方案文件json
        日期：20250926
        """
        self._last_adwaynum_cache_meta = {'from_official_file': None}
        self._update_git_config()
        # 定义时间槽到目录名称的映射
        time_slot_mapping = {
            1: ["[0,7)天", "0~7"],
            2: ["[7,31)天", "7~31"],
            3: ["[31，+∞)天", "31+"],
            0:None
        }
        business_dir = self.project_dir
        if business_v:
            business_dir = joint_path(self.project_dir, business_v)
        if not exists(business_dir):
            return {"error": f"目录不存在"}
        if not business_v:
            try:
                slot_key = str(int(time_slot))
            except (TypeError, ValueError):
                slot_key = str(time_slot)
            plock = _project_adwaynum_lock(self.project_name)
            with plock:
                slots = self._load_official_slots_from_file()
                if slots is not None and slot_key in slots:
                    self._last_adwaynum_cache_meta = {'from_official_file': True}
                    return slots[slot_key]
                built = self._sync_build_official_slots_ios_inner()
                if isinstance(built, dict) and built.get('error'):
                    return built
                self._atomic_write_official_slots(built)
                self._last_adwaynum_cache_meta = {'from_official_file': False}
                return built.get(slot_key, [])
        first_level_include_dirs = self.get_business_v().copy()
        if business_v:
            first_level_include_dirs = []
        exclude_names = ['test']
        result = self.recursion_get_file(
            path=business_dir,
            include_names=time_slot_mapping.get(time_slot),
            is_sort=True,
            exclude_names=exclude_names,
            first_level_include_dirs=first_level_include_dirs,
        )
        self._last_adwaynum_cache_meta = {'from_official_file': None}
        return result


    def get_ios_adwaynum_json_v2(self, business_v,adwaynum_name):
        """获取ios方案json"""
        try:
            business_dir = joint_path(self.project_dir, f"{business_v}")
            adwaynum_path = joint_path(business_dir, adwaynum_name.replace(self.split_label, "/") + ".json")

            self._update_git_config()

            if exists(adwaynum_path):
                result = self._dict_sorted(self._get_ios_json_v2(adwaynum_path), sort_status=True)
                return result
            return {"error": "没有相关目录"}

        except Exception as e:
            return {"error": f"服务器异常{e}"}


    def recursion_dir(self,path, pre=None,exclude_names: list =None,first_level_include_dirs:list=None):
        """
        递归目录
        :return:
        """
        pre = pre if pre else []
        stack = [(pre, path)]
        while stack:
            pre, path = stack.pop()
            # 获取目录
            if first_level_include_dirs:
                # 保存第一级目录，在第一级目录下进行递归
                dirs=first_level_include_dirs
                first_level_include_dirs=[]   # 清除，后面会根据已有目录进行递归
            else:
                dirs = get_directory_file(path, folder_only=True, filter_dot_prefix=False)
            # 过滤目录
            if exclude_names:
                dirs = [dir for dir in dirs if dir not in exclude_names]
            if dirs:
                # 有目录
                for dir in dirs:
                    # 拼接下级路径
                    next_path = joint_path(path, dir)
                    # 拼接目录层级
                    new_pre = pre + [dir]
                    stack.append((new_pre, next_path))
            # 没有目录则获取文件
            files = get_directory_file(path, include_names=['.json'], filter_dot_prefix=False)
            if files:
                files.sort(reverse=True)  # 保持原排序逻辑
                for file in files:
                    new_pre = pre + [get_folder_name(file, is_extension=False)]
                    yield new_pre

    def _get_persist_data(self):
        """
        获取缓存数据
        """
        persist_data_list=[]
        persist_data_file=joint_path(self.cache_data.persist_dir,"git_cache_data.json")

        if exists(persist_data_file):
            persist_data_list=self.cache_data.get(key=self.project_name,default=persist_data_list)
        return persist_data_list

    def _recursion_collect_files_flat(self, path, exclude_names=None, first_level_include_dirs=None):
        """不做 persist 短路，全量扫描目录生成方案路径列表（与 recursion_get_file 数据源一致）。"""
        files_result = []
        file_lists = self.recursion_dir(
            path, exclude_names=exclude_names, first_level_include_dirs=first_level_include_dirs
        )
        for file_list in file_lists:
            files_result.append(f'{self.split_label}'.join(file_list))
        return files_result

    @staticmethod
    def _apply_slot_include_filter(files_result, include_names):
        if not include_names:
            return list(files_result)
        return [
            item
            for item in files_result
            if any(
                (sub == '31day' and sub in item and '31day_later' not in item)
                or (sub != '31day' and sub in item)
                for sub in include_names
            )
        ]

    def _slots_from_full_list(self, full_list, time_slot_mapping, is_sort):
        slots = {}
        for slot in range(4):
            inc = time_slot_mapping.get(slot)
            fr = self._apply_slot_include_filter(full_list, inc)
            fr.sort(key=self._dir_custom_sort, reverse=is_sort)
            slots[str(slot)] = fr
        return slots

    def _sync_build_official_slots_gp_inner(self):
        """期数为空时构建各 time_slot 列表；失败返回 {'error': ...}。"""
        first_level_include_dirs = self.get_business_v().copy()
        business_dir = self.project_dir
        if not exists(business_dir):
            return {'error': '目录不存在'}
        full = self._recursion_collect_files_flat(
            business_dir, exclude_names=None, first_level_include_dirs=first_level_include_dirs
        )
        try:
            self.cache_data.put(self.project_name, full)
        except Exception as e:
            logger.warning('persist adwaynum full list failed %s: %s', self.project_name, e)
        return self._slots_from_full_list(full, _GP_ADWAYNUM_SLOT_MAP, True)

    def _sync_build_official_slots_ios_inner(self):
        first_level_include_dirs = self.get_business_v().copy()
        exclude_names = ['test']
        business_dir = self.project_dir
        if not exists(business_dir):
            return {'error': f'目录不存在'}
        full = self._recursion_collect_files_flat(
            business_dir, exclude_names=exclude_names, first_level_include_dirs=first_level_include_dirs
        )
        try:
            self.cache_data.put(self.project_name, full)
        except Exception as e:
            logger.warning('persist adwaynum full list failed %s: %s', self.project_name, e)
        return self._slots_from_full_list(full, _IOS_ADWAYNUM_SLOT_MAP, True)

    def _atomic_write_official_slots(self, slots_dict):
        path = _adwaynum_official_cache_path(self.project_name)
        tmp = f'{path}.tmp'
        payload = {
            'project_name': self.project_name,
            'slots': {str(k): v for k, v in slots_dict.items()},
            'updated_at': time.time(),
        }
        with open(tmp, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(tmp, path)

    def _load_official_slots_from_file(self):
        path = _adwaynum_official_cache_path(self.project_name)
        if not exists(path):
            return None
        try:
            with open(path, encoding='utf-8') as stream:
                data = json.load(stream)
            return data.get('slots')
        except (json.JSONDecodeError, OSError) as e:
            logger.warning('read adwaynum official cache %s: %s', path, e)
            return None

    def recursion_get_file(self,path, split_label="--",include_names=None,is_sort=False,exclude_names:list=None,first_level_include_dirs:list=None):
        """
        递归获取目录下的文件
        :params    include_names   要包含的目录
        :params    is_sort   排序方式
        :params    exclude_names   排序方式
        :params    first_level_include_dirs   第一层级目录
        """
        files_result = []
        # file_lists = self.recursion_dir(path, exclude_names=exclude_names,
        #                                 first_level_include_dirs=first_level_include_dirs)
        # for file_list in file_lists:
        #     files_result.append(f"{split_label}".join(file_list))
        # 获取缓存数据
        persist_data=self._get_persist_data()
        if not persist_data:
            file_lists = self.recursion_dir(path,exclude_names=exclude_names,first_level_include_dirs=first_level_include_dirs)
            for file_list in file_lists:
                files_result.append(f"{split_label}".join(file_list))
            self.cache_data.put(key=self.project_name, value=files_result)
        else:
            files_result = persist_data.copy()
        # 过滤不包含目录的
        if include_names:
            files_result = [item for item in files_result
                      if any((sub == "31day" and sub in item and "31day_later" not in item)
                             or (sub != "31day" and sub in item)
                             for sub in include_names)]
        # 排序
        files_result.sort(key=self._dir_custom_sort, reverse=is_sort)
        return files_result

    def get_gp_adwaynum_file(self,time_slot,business_v=None):
        """
        获取方案文件
        :params    business_v       期数
        """
        self._last_adwaynum_cache_meta = {'from_official_file': None}
        self._update_git_config()
        time_slot_mapping = {
            1: ["7day"],
            2: ["31day"],
            3: ["31day_later"],
            0:None
        }
        business_dir=self.project_dir
        if business_v:
            business_dir=joint_path(self.project_dir,business_v)
        if not exists(business_dir):
            return {"error":"目录不存在"}
        if not business_v:
            try:
                slot_key = str(int(time_slot))
            except (TypeError, ValueError):
                slot_key = str(time_slot)
            plock = _project_adwaynum_lock(self.project_name)
            with plock:
                slots = self._load_official_slots_from_file()
                if slots is not None and slot_key in slots:
                    self._last_adwaynum_cache_meta = {'from_official_file': True}
                    return slots[slot_key]
                built = self._sync_build_official_slots_gp_inner()
                if isinstance(built, dict) and built.get('error'):
                    return built
                self._atomic_write_official_slots(built)
                self._last_adwaynum_cache_meta = {'from_official_file': False}
                return built.get(slot_key, [])
        first_level_include_dirs = self.get_business_v().copy()
        if business_v:
            first_level_include_dirs=[]
        result=self.recursion_get_file(path=business_dir,include_names=time_slot_mapping.get(time_slot),is_sort=True,first_level_include_dirs=first_level_include_dirs)
        self._last_adwaynum_cache_meta = {'from_official_file': None}
        return result


    def _dir_custom_sort(self,dir_path):
        """
        目录排序
        """
        temp_list=[]
        parts=dir_path.split('--')
        # temp_list.append(len(parts))
        for i in range(len(parts)):
            match = re.search(r'\d+', parts[i])
            if match:
                number = int(match.group())  # 提取数字部分
            else:
                number = 0
            temp_list.append(len(str(number)))
        return tuple(temp_list)

    def _get_gp_json_by_ab_v3(self,adwaynum_path):
        """获取json文件"""
        adwaynum_json_map={}
        adwaynum_list = self._read_json(adwaynum_path)
        if isinstance(adwaynum_list,list):
            for adwaynum_json in adwaynum_list:
                country_list = adwaynum_json.get("country_list", [])
                country_list.sort(reverse=True)
                # 判断国家列表不为空时，取第一个国家
                if country_list:
                    country = self._country_cn_mapping(country_list[0], len(country_list))
                    ad_info = adwaynum_json.get("ad_info", {})
                    ad_info["country_list"] = country_list
                    self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                country_key=country,
                                                add_data=self.sort_dict_by_v1(ad_info))
                else:
                    country="其他"
                    ad_info = adwaynum_json.get("ad_info", {})
                    self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                                country_key=country,
                                                add_data=self.sort_dict_by_v1(ad_info))
        else:
            # 处理dict_data层数据
            dict_data_info=adwaynum_list.get("dict_data",{})
            for dict_data_key,dict_data_map in dict_data_info.items():
                self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                            country_key=dict_data_key,
                                            add_data=self.sort_dict_by_v1(dict_data_map))
            # 处理install_day_filters层数据
            install_day_filters=adwaynum_list.get("install_day_filters",[])
            for install_day_info in install_day_filters:
                key_name="install_day_"+str(install_day_info.get("install_day","-1"))
                self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                            country_key=key_name,
                                            add_data=self.sort_dict_by_v1(install_day_info))
        return adwaynum_json_map

    def _get_gp_huci_json(self,adwaynum_path):
        """互斥方案"""
        adwaynum_json_map = {}
        adwaynum_json_data = self._read_json(adwaynum_path)
        ab_replace_data=adwaynum_json_data.get("ab_replace", {})
        for adwaynum_type in ab_replace_data:
            json_data=json.loads(ab_replace_data.get(adwaynum_type, {})).get("value",{})
            # 处理dict_data层数据
            dict_data_info = json_data.get("dict_data", {})
            for dict_data_key, dict_data_map in dict_data_info.items():
                key_name =adwaynum_type+"--"+dict_data_key
                self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                            country_key=key_name,
                                            add_data=self.sort_dict_by_v1(dict_data_map))
            # 处理install_day_filters层数据
            install_day_filters = json_data.get("install_day_filters", [])
            for install_day_info in install_day_filters:
                key_name = adwaynum_type+"--install_day_" + str(install_day_info.get("install_day", "-1"))
                self._add_adwaynum_json_map(adwaynum_json_map=adwaynum_json_map,
                                            country_key=key_name,
                                            add_data=self.sort_dict_by_v1(install_day_info))
        return adwaynum_json_map




if __name__ == '__main__':
    read_git_config = ReadGitConfig(project_name="gp_blockblast")
    async_rebuild_adwaynum_file_cache("gp_blockblast_orth")
    # read_git_config._get_gp_json_by_ab_v3("/Users/admin/Desktop/ZnYan/hsabtest_config/gp_blockblast_orth/not_distinguish_lifecycle/since9.1.0/reward/608-2-2/rv608603.json")
    # print(json.dumps(read_git_config.get_gp_adwaynum_file(business_v="",time_slot=1),ensure_ascii=False))
    # print(json.dumps(read_git_config.recursion_get_file(read_git_config.project_dir,first_level_include_dirs=exclude_names),ensure_ascii=False))
    # print(json.dumps(read_git_config.get_ios_adwaynum_file_v2(business_v="",time_slot=0)))
    # print(read_git_config.get_adwaynum_file_v2(business_v="V995",time_slot=1))
    # print(read_git_config.get_gp_adwaynum_json_v4(business_v="",adwaynum_name="113--113_31day_later--113203",time_slot=0))
    # print(read_git_config.cache_data.persist_dir)
