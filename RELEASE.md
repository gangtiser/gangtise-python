# 发版清单

1. 本地全量测试全绿：
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src
   uv run pytest -m "not live"
   uv build
   ```
   🔴 **还要跨时区跑一遍——CI 跑在 UTC，本机是 CST。** 凡是把墙上时间换算成绝对时刻的逻辑，与按本地时区锚定的测试只在编写该测试的那个时区里结果一致，所以本地全绿证明不了 CI 也会绿：
   ```bash
   for TZ in UTC America/Los_Angeles Pacific/Kiritimati Australia/Lord_Howe America/New_York; do
     TZ=$TZ uv run pytest -m "not live" -q || echo "FAILED under $TZ"
   done
   ```
   v0.4.0 的 tag 被打红，就是因为跳过了这一步：换算已改为北京时间锚点，但有 12 条测试仍按旧的本地锚点断言，它们在本机全部通过，在 CI runner 上全部失败。
2. 真机集成测试——**仅当本次发版涉及接口/API 表面时才必须跑**（新增或改动的接口、请求体字段形状、错误码处理）：
   ```bash
   uv run pytest -m live   # 需要真实凭证，会扣积分
   ```
   这些测试会打到按次**计费**、不自动重发的接口（如 `concept_info`），因此不涉及接口/API 表面改动的纯内部补丁（例如加固下载路径的发版）可以跳过——强制关卡是第 1 步（`-m "not live"` + ruff + format + mypy + build）。若跳过，须在 commit 正文中注明。
3. 在 `CHANGELOG.md` 中加上新版本小节，并在 `README.md` 中更新对应的「最近 5 个版本」条目；发版 CI 在发布前会检查这两处。开发期间两处的标题写作 `## [X.Y.Z] - Unreleased` / `### X.Y.Z - 未发布`，**打 tag 前必须换成发布日期**（`## [X.Y.Z] - YYYY-MM-DD` / `### X.Y.Z - YYYY-MM-DD`）——CI 要求标题后跟日期，占位符会被拦下。
4. 升级 `src/gangtise_openapi/__about__.py` 中的版本号（`__version__`）。

   > ⚠️ **核对版本号要看 `__about__.py` 和 `dist/` 里构建出的文件名，绝不要看 `pip list` / `importlib.metadata.version()`。** editable 安装记录的是安装当时的版本，并不会跟随之后的版本升级，所以 `importlib.metadata.version("gangtise-openapi")` 可能报出旧版本号，而 `__about__.__version__`、`USER_AGENT` 和构建产物其实都是对的。查错了对象，正确的升级就会被「确认」为有问题——更糟的是，漏掉的升级会被确认为已完成。
5. 提交：`git add -A && git commit -m "release: vX.Y.Z"`。（要用 `git add -A`，**不要**用 `git commit -am`——`-am` 会漏掉新增的未跟踪文件，若本次发版新增了领域文件或示例文件，发出去的代码树在干净 checkout 上会导入失败。）
6. 打 tag：`git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin main vX.Y.Z`。（不要用 `--follow-tags`：它不推 lightweight tag，v0.1.0/v0.1.4 都因此没触发发布 workflow。）
7. CI workflow `.github/workflows/release.yml` 依次执行构建、发布和创建 GitHub Release。
8. **撰写 GitHub Release 说明**——workflow 用 `--generate-notes` 创建 release，说明内容取自 PR。本仓库直接提交到 `main`，所以生成的正文只有一个「Full Changelog」链接（v0.1.x 到 v0.3.0 全是这样发出去的）。决定*要不要升级*的人看的是这个页面，而不是 `CHANGELOG.md`，所以要把破坏性变更和「这里原本就是坏的，升级即修复」类条目放在最前面：
   ```bash
   gh release edit vX.Y.Z --notes-file <file>
   ```
   措辞纪律与 `README.md` 相同：不写平台内容库的绝对规模；描述服务端行为时，写成可观察到的结果 + 该怎么做。
9. 在 PyPI 上验证：在干净的 venv 里 `pip install gangtise-openapi==X.Y.Z`（uv 会缓存元数据——要用 `uv pip install --refresh-package gangtise-openapi`）。

   > ⚠️ **发布后的最初几分钟里，PyPI 的任何元数据端点都不可信，也不存在哪个是「靠得住」的那个。** v0.3.1 上的实测：`/pypi/<pkg>/json` 与 `/pypi/<pkg>/<ver>/json` 带有*相同的* `cache-control: max-age=900`，`/simple/<pkg>/` 带 `max-age=600`，三者返回的都是 Fastly `x-cache: ... HIT`。发布后约 2 分钟内，包级 URL 上出现过两种失败形态：**空响应体**（用 `curl -s` 时只会在下游表现为 JSON 解析错误），以及**完整但陈旧的响应体**——58KB、合法 JSON，`info.version` 仍是上一版，`releases` 里也没有新版本。版本级 URL 那天之所以正确，只是因为这个缓存键从未被填充过；若在发布*之前*请求过它，404 一样会被缓存下来。
   >
   > 所以要把三者当作三个独立的缓存键：**三者一致才是信号，其中任何一个单独给出的否定答案都不能证明发布失败。** 这一点之所以要紧，是因为假阴性诱导出的动作是「tag 没发出去，挪一下/重打 tag」——而这个 tag 已经推送出去了。
   >
   > 查询你刚发布的那个具体版本，绝不要查 `latest`。还要注意，元数据只能说明*有东西*到了；判断*到的是对的东西*要看行为——把发布出去的产物装进一个一次性环境，实际跑一遍本次发版涉及的改动，并断言 `gangtise_openapi.__file__` 不在本地工作区（否则测的是你自己的源码树，不管上传了什么都会通过）。

## 已知的发布失败

`InvalidDistribution: '2.5' is not a valid metadata version`——固定版本的 `pypa/gh-action-pypi-publish` 自带的 twine 太旧，不认 hatchling 产出的元数据版本。**修 action 的固定版本，不要给 hatchling 封顶**：metadata 2.5 是 PyPI 接受的标准版本，给 hatchling 封顶等于为了迁就一个过时的工具而背离标准。v1.14.2 是第一个自带 twine（v7）能接受 2.5 的版本，固定版本必须不低于它。v0.3.0 遇到过此问题——发布失败，没有任何东西传到 PyPI，于是把 tag 挪到了修复提交上，而没有烧掉这个版本号。

## 发布配置

PyPI 通过 Trusted Publishing（OIDC）发布，不使用 API token。`gangtise-openapi` 项目设置里的 Trusted Publisher：

- Owner：`gangtiser`
- Repository：`gangtise-python`
- Workflow：`release.yml`
- Environment：（留空）

改仓库名、workflow 文件名或启用 environment 时，要同步改 PyPI 侧的这项配置，否则发布步骤会在 OIDC 校验时失败。需要先在 TestPyPI 演练时，临时给固定版本的 `pypa/gh-action-pypi-publish` 步骤加上 `repository-url: https://test.pypi.org/legacy/`，打正式 tag 前改回来。
