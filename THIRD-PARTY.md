# 第三方组件与许可（Third-Party Components）

本仓库不是单一作品，而是几份不同授权的东西拼起来的。这里逐项写清：**谁的作品、什么版本、
在哪、有没有被改、什么许可、源码去哪拿**。

> 本文件是给使用者和再分发者的说明，不构成法律意见。
> 若你要再分发（打包、镜像、做安装器、放进你自己的发行版），请照下表把对应的许可文本一起带上。

## 一、数据

| 组件 | 位置 | 来源 / 版本 | 许可 | 是否修改 | 义务 |
|---|---|---|---|---|---|
| Eldamo 词库 | `data/eldamo-data.xml`、`data/elvish.db` | [Eldamo](https://eldamo.org) v0.8.13（2026-06-01 生成），© Paul Strack | [CC-BY 4.0](LICENSES/CC-BY-4.0.txt) | **是**：解析成 SQLite、加了检索字段与派生分类 | 署名 Paul Strack + 链接许可 + 说明本仓库做了改动 |

Eldamo 的原始文件（`eldamo-data.xml`）原样收录，未作内容改动；`elvish.db` 是由它派生的数据库。

## 二、运行时库（二进制随本仓库分发）

| 组件 | 位置 | 来源 / 版本 | 许可 | 是否修改 | 源码获取 |
|---|---|---|---|---|---|
| eSpeak NG | `assets/espeak/libespeak_ng.dll`、`assets/espeak/espeak-ng-data/` | [espeak-ng 1.52.0](https://github.com/espeak-ng/espeak-ng/releases/tag/1.52.0) | [GPL-3.0](LICENSES/GPL-3.0.txt) | 否（仅按 espeak 期望的目录结构整理过数据文件位置） | 上游 tag `1.52.0`：<https://github.com/espeak-ng/espeak-ng/tree/1.52.0> |

引用的方式：`app/speech.py` 用 `ctypes` 动态加载该 DLL，只调公开 API
（`espeak_Initialize` / `espeak_SetVoiceByName` / `espeak_Synth` 等），未静态链接、未改动其代码。

## 三、字体

| 组件 | 位置 | 来源 | 许可 | 源码获取 |
|---|---|---|---|---|
| FreeMonoTengwar | `assets/tengwar-font/` | [Free Tengwar Font Project](https://freetengwar.sourceforge.net/)（2013-07-21） | GPL + 字体嵌入例外（随包 `GPL.txt`） | 同目录 `FreeMonoTengwar.sfd` 可向项目索取；上游站点提供 |
| FreeSerif | `assets/freefont/freefont-20120503/` | [GNU FreeFont](https://www.gnu.org/software/freefont/)（20120503） | GPL + 字体例外（随包 `COPYING`） | 同目录 `COPYING`/`CREDITS`，上游站点提供 |

## 四、构建期依赖（**不随仓库分发**）

| 组件 | 版本 | 许可 | 说明 |
|---|---|---|---|
| [Glǽmscribe](https://github.com/BenTalagan/glaemscribe) | 1.3.1 | AGPL-3.0 | 由 `npm install` 从 npm 拉取，`.gitignore` 已排除 `node_modules/`；本仓库不含其代码，也未修改它 |

因为本项目要调用 Glǽmscribe，**本仓库整体以 AGPL-3.0 发布**（见根目录 `LICENSE`）。
AGPL-3.0 与 GPL-3.0 可由 AGPL 侧合并（GPLv3 §13），因此上述组合是许可兼容的。

## 五、再分发检查清单

- [ ] 保留根目录 `LICENSE`（AGPL-3.0）与 `LICENSES/` 全部文本
- [ ] 保留 `assets/NOTICE.txt` 与本文件
- [ ] 保留 Eldamo 的署名（Paul Strack）与 CC-BY 链接，并说明你做的改动
- [ ] 保留 `assets/espeak/`、字体目录里各自的 GPL 文本
- [ ] 若你把 Glǽmscribe 打进你的包，你的包也必须是 AGPL-3.0 并提供完整源码
- [ ] 若你把它做成**网络服务**（AGPL §13），要在界面上提供获取源码的入口

## 关于托尔金（不是许可问题，单独提醒）

昆雅语、腾格瓦字母、《魔戒》相关的名称与设定，其版权与商标权属于 Tolkien Estate 与
Middle-earth Enterprises 等权利人，**不在上面任何开源许可的授权范围内**。

本仓库只在以下意义上使用它们：作为**语言学研究的对象**引用词语与其出处，以及提供学习工具。
仓库不包含《魔戒》等作品的正文、影视素材、官方标识，也不声称获得授权。

如果你要基于它做公开宣传或再发布，请：

- 明确标注「同人 / 非官方 / 免费」，不要使用「官方」「授权」「联名」等表述；
- 不要使用电影、剧集的画面、原声、海报或官方 logo；
- 不要把它作为商品出售，也不要把相关名称注册为商标。

以上是风险提示，不构成法律意见；涉及实际发行前，建议咨询专业律师。
