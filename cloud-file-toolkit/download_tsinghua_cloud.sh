#!/bin/bash
# 用法: ./download.sh <share_token> [目标目录]
# share_token 是分享链接 https://cloud.tsinghua.edu.cn/d/XXXXX/ 里的 XXXXX

TOKEN="$1"
OUTDIR="${2:-./download}"
REF_DIR="${3:-}"
BASE="https://cloud.tsinghua.edu.cn"

mkdir -p "$OUTDIR"

# 获取文件列表并下载
curl -s "$BASE/api/v2.1/share-links/$TOKEN/dirents/?path=/" \
  | jq -r '.dirent_list[] | select(.is_dir==false) | .file_name' \
  | while read -r fname; do
      echo "下载: $fname"
      curl -L -C - -o "$OUTDIR/$fname" \
        "$BASE/d/$TOKEN/files/?p=/$(printf '%s' "$fname" | jq -sRr @uri)&dl=1"
    done

echo ""
echo "=== SHA256 校验 ==="

pass=0
fail=0
missing=0

for ref_file in "$REF_DIR"/*; do
    fname=$(basename "$ref_file")
    check_file="$OUTDIR/$fname"

    if [ ! -f "$check_file" ]; then
        echo "MISSING : $fname (not found in $OUTDIR)"
        ((missing++))
        continue
    fi

    ref_sum=$(shasum -a 256 "$ref_file" | awk '{print $1}')
    check_sum=$(shasum -a 256 "$check_file" | awk '{print $1}')

    if [ "$ref_sum" = "$check_sum" ]; then
        echo "OK      : $fname"
        ((pass++))
    else
        echo "MISMATCH: $fname"
        echo "  ref  : $ref_sum"
        echo "  check: $check_sum"
        ((fail++))
    fi
done

echo ""
echo "结果: $pass OK, $fail MISMATCH, $missing MISSING"
