#!/bin/bash
# Check SHA256 of specific files between two directories

CHECK_DIR="/Users/yuhang/Downloads/0419_split_200M_check"
REF_DIR="/Users/yuhang/Downloads/0419_split_200M"

FILES=(
    "0419_59999_aq"
    "0419_59999_ar"
    "0419_59999_av"
    "0419_59999_bd"
    "0419_59999_au"
    "0419_59999_ay"
)

pass=0
fail=0
missing=0

echo "=== SHA256 校验 ==="

for fname in "${FILES[@]}"; do
    ref_file="$REF_DIR/$fname"
    check_file="$CHECK_DIR/$fname"

    if [ ! -f "$check_file" ]; then
        echo "MISSING : $fname"
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
