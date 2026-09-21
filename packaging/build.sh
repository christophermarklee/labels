#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build_dir="$project_dir/build/rpmbuild"
for tool in rpmbuild rpm2cpio cpio python3; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
mkdir -p "$build_dir"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS,tmp}
cp "$project_dir/drivers/ql810wpdrv-3.1.5-1.i386.rpm" "$build_dir/SOURCES/"
cp "$project_dir/packaging/prepare.py" "$build_dir/SOURCES/"
cp "$project_dir/packaging/ql810wpdrv.spec" "$build_dir/SPECS/"
rpmbuild -ba --define "_topdir $build_dir" --define "_tmppath $build_dir/tmp" "$build_dir/SPECS/ql810wpdrv.spec"
cp "$build_dir/RPMS/x86_64/ql810wpdrv-3.1.5-2.local.el10.x86_64.rpm" "$project_dir/drivers/"
cp "$build_dir/SRPMS/ql810wpdrv-3.1.5-2.local.el10.src.rpm" "$project_dir/drivers/"
