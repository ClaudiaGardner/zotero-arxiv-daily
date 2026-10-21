# 个人研究日报

部署仓库：https://github.com/ClaudiaGardner/zotero-arxiv-daily

每天北京时间 09:07 由 GitHub Actions 启动（UTC cron：`7 1 * * *`），收件人为 `RECEIVER` Secret 中的邮箱。避开整点调度高峰；Actions 可能延迟启动，邮件在检索、排序和生成摘要完成后发送。

## 阅读偏好

关注 LLM agents、多智能体、人机交互、游戏 agent、LLM、MLLM、生成模型、世界模型，以及 JEPA/联合嵌入预测架构（I-JEPA、V-JEPA、潜空间预测与非生成式世界模型）。配置保存在 `config/research.yaml`，实际运行使用仓库 Variable `CUSTOM_CONFIG` 中的同一份内容。

- 使用明确配置的兴趣作为相似度排序目标，无需 Zotero 账户或文库。
- 检索 arXiv 新论文及 cross-list、最近三天 Hugging Face Daily Papers、Crossref 最近索引的会议论文。
- arXiv RSS 为空时，按分类检索最近七天首次提交的论文，每分类最多八十条，覆盖周末和发布时间空窗；跨日去重避免重复发送。
- Crossref 会议检索限定最近九十天发表的论文，包含 proceedings article 和以书籍章节登记的会议论文；先按会议名称匹配度检索，再校验会议元数据与首次发表日期，排除 workshop、companion 和旧论文重新上线。每个会议每次最多一百条；覆盖受公开元数据限制，不保证每天有顶会录用论文。
- 会议来源包括 CHI、UIST、NeurIPS、ICML、ICLR、AAAI、IJCAI、ACL、EMNLP、CVPR、ICCV、ECCV、ACM MM、AAMAS、CoRL；实际覆盖取决于公开源的收录情况。
- 有会议出处证据的论文获得排序加成；arXiv 和 Hugging Face 本身不表示会议录用。
- 保留 arXiv 备注中的明确录用声明，邮件标为“作者声明”，与会议来源元数据区分；投稿中和 workshop 不获得该优先级。
- 每期最多二十五篇，期刊最多两篇。先进行主题相似度召回，再对前一百篇的标题、摘要和会议元数据进行模型筛选，检查方向匹配、具体方法价值和描述的验证证据。关闭强制关键词置顶；同一主方向最多八篇，减少世界模型等词汇垄断。筛选不足时少发，不靠弱相关论文凑数。该阶段是基于摘要的筛选估计，完整解读随后依据正文生成。
- **学术背书门槛**：解读生成前逐篇检查三类独立证据，至少命中一项才进入日报：(1) 会议——来源元数据或 arXiv 作者声明的正式录用，workshop、投稿中、Findings 不算；(2) 学者——作者姓名与代码内置的知名研究者名单精确匹配；(3) 实验室——论文首页作者单位与内置的知名实验室/机构名单匹配，摘要正文不参与匹配。名单可在 `research.authority.extra_scholars`、`extra_labs`、`extra_venues` 中追加。筛选阶段多保留十五篇候选用于补位；通过门槛的不足二十五篇时按实际数量发送，不凑数。邮件逐篇标注命中的证据。
- 邮件显示实际发布时间：arXiv 首次发布日期与最近更新分列；会议论文使用来源的发表日期。HF 推荐日、Crossref 索引日和检索日不能代替发表日期；年份或年月按来源精度显示，未取得日期时明确标注。
- DeepSeek `deepseek-v4-pro` 优先依据 arXiv HTML/PDF 正文生成简体中文学术解读，目标每篇约二百八十至四百五十字。正文只包含 Motivation、方法、创新点三部分，使用直白、简洁、干练的学术语言。
- 解读生成失败时只重试一次；仍不满足三段结构的论文暂不发送，保留到后续检索，不用原摘要凑数。论文正文中的 tokenizer 特殊标记按普通文本处理。
- 长论文优先选取方法、实验、结果和局限段落，输入上限一万六千 token；PDF 读取前二十四页及末尾三页。邮件明确标注实际阅读依据，全文无法取得时回退为摘要，并说明未能核验的细节。
- 每篇优先选择能说明框架、方法或整体流程的一张主图。优先使用论文 HTML 图片，必要时从 PDF 前六页按图注定位并裁剪，保留原文图注；无法可靠取得时不插图。图片作为 CID 内嵌附件随邮件发送，单图压缩到约四百 KB，预览 HTML 使用内嵌图片数据。
- arXiv、HF、会议之间按论文标识和标题去重；已成功发送的论文标识存储为 Fernet 加密状态。
- 没有新推荐时仍发送一封空日报。预览不发送邮件，也不更新已发送状态。

## 邮件配置

发件人与收件人均已设为 QQ 邮箱，`SENDER_PASSWORD` Secret 已配置。更换 SMTP 授权码时在以下页面更新 Secret：

https://github.com/ClaudiaGardner/zotero-arxiv-daily/settings/secrets/actions/new

名称为 `SENDER_PASSWORD`，值为 QQ 邮箱 SMTP 授权码。使用 `smtp.qq.com:465` 的 SSL 连接。授权码无需写入代码或 `CUSTOM_CONFIG`。

如果更换发件邮箱，请同步修改 `SENDER` Secret，以及 `CUSTOM_CONFIG` 内的 SMTP 主机、端口；`RECEIVER` 保持收件邮箱。

## 验证与维护

Fork 后先在仓库 Actions 页面点击 “I understand my workflows, go ahead and enable them”，再分别启用 “Send emails daily” 和 “Keep Alive”。确认两者状态为 `active`，而不是 `disabled_fork`。仅能手动运行不代表自动调度已启用。

自动调度以 Actions 中事件为 `schedule` 的实际运行记录为验证依据；`workflow_dispatch` 只证明手动运行成功。

在 Actions 的 “Send emails daily” 工作流中选择 “Run workflow”：

- `preview=true`：生成邮件 HTML，下载 `daily-papers-preview` Artifact 查看。
- `preview=false`：真实发信，需已有 `SENDER_PASSWORD`。
- `refresh_digest=true`：手动生成改版样例，允许重新解读已发送过的近期论文。默认关闭，不影响日常去重。

“Keep Alive” 工作流定期提交维护记录，避免公开仓库长期无活动导致定时任务停用。

更新阅读偏好后，将 `config/research.yaml` 的完整内容同步到 `CUSTOM_CONFIG`。API 凭据存放在 `OPENAI_API_KEY` Secret，服务地址存放在 `OPENAI_API_BASE` Secret。
