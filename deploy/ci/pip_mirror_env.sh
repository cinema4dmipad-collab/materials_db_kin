#!/bin/sh
# Выбор pip index: pypi.org или первое доступное зеркало.
# Только env-переменные — poetry.lock не меняется.

export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-120}"
export PIP_RETRIES="${PIP_RETRIES:-10}"

_pip_probe() {
    curl -sf --max-time 12 -I "$1" >/dev/null 2>&1
}

_pip_host_from_url() {
    printf '%s\n' "$1" | sed -E 's#^https?://([^/]+)/?.*$#\1#'
}

_pip_use_mirror() {
    host="$1"
    url="$2"
    export PIP_INDEX_URL="$url"
    export PIP_TRUSTED_HOST="$host"
    echo "Используем зеркало: $host"
}

_pip_mirror_select() {
    if [ -n "${PIP_INDEX_URL:-}" ]; then
        host="${PIP_TRUSTED_HOST:-$(_pip_host_from_url "$PIP_INDEX_URL")}"
        export PIP_TRUSTED_HOST="$host"
        echo "Используем заданный PIP_INDEX_URL: $PIP_INDEX_URL"
        return 0
    fi

    if _pip_probe "https://pypi.org/simple/pip/"; then
        echo "PyPI доступен (pypi.org)."
        return 0
    fi

    echo "PyPI недоступен — проверяем зеркала..."

    mirrors="${PIP_MIRROR_URLS:-https://pypi.tuna.tsinghua.edu.cn/simple/ https://mirrors.aliyun.com/pypi/simple/ https://pypi.mirrors.ustc.edu.cn/simple/ https://repo.huaweicloud.com/repository/pypi/simple/ https://pypi.douban.com/simple/}"
    for url in $mirrors; do
        host="$(_pip_host_from_url "$url")"
        if _pip_probe "${url%/}/pip/"; then
            _pip_use_mirror "$host" "$url"
            return 0
        fi
        echo "  недоступно: $host"
    done

    echo "WARNING: ни одно зеркало не ответило на probe — fallback Tsinghua"
    _pip_use_mirror "pypi.tuna.tsinghua.edu.cn" "https://pypi.tuna.tsinghua.edu.cn/simple/"
}

_pip_mirror_select
