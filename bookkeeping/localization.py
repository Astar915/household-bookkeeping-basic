from __future__ import annotations

import json
import os
import re
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # Headless web hosting only uses translation helpers.
    tk = filedialog = messagebox = ttk = None
from pathlib import Path
from typing import Any
from .user_data import app_data_directory


DEFAULT_LANGUAGE = "zh-CN"
LANGUAGE_CHOICES = (
    ("zh-CN", "简体中文"),
    ("ja-JP", "日本語"),
    ("en-US", "English"),
)


# Keep Chinese source strings as stable translation keys. Account names,
# categories entered by the user, chat content, and Skill text remain data and
# are not translated unless they are fixed UI labels.
_ROWS: tuple[tuple[str, str, str], ...] = (
    ('界面发生错误，详细位置已保存至本机诊断日志。', '画面エラーの発生箇所をローカル診断ログに保存しました。', 'UI error locations were saved in the local diagnostic log.'),
    ('正在等待模型回复（{seconds} 秒），可随时中断。', 'モデルの応答待ち（{seconds}秒）。いつでも中断できます。', 'Waiting for the model ({seconds}s). You can interrupt at any time.'),
    ('正在检查云端最新账本…', 'クラウドの最新台帳を確認中…', 'Checking the latest cloud ledger…'),
    ('已自动下载最新云端账本，恢复前已备份本机数据。', '最新のクラウド台帳を取得しました。復元前のデータはバックアップ済みです。', 'Latest cloud ledger downloaded. A recovery backup was saved first.'),
    ('当前已是最新云端账本。', 'クラウド台帳は最新です。', 'The cloud ledger is already up to date.'),
    ('自动下载未完成：{error}', '自動ダウンロード未完了：{error}', 'Automatic download did not complete: {error}'),
    ('云端下载检查点损坏，请先检查本机备份。', 'クラウド取得情報が破損しています。ローカルのバックアップを確認してください。', 'Cloud download checkpoint is damaged. Check the local backup.'),
    ('云端备份清单过大。', 'クラウドのバックアップ一覧が大きすぎます。', 'Cloud backup manifest is too large.'),
    ('云端备份时间缺少时区。', 'クラウドのバックアップ日時にタイムゾーンがありません。', 'Cloud backup date has no time zone.'),
    ('无法检查云端账本，请检查网络与云端授权。', 'クラウド台帳を確認できません。接続と認証を確認してください。', 'Cannot check the cloud ledger. Check the connection and authorization.'),
    ('自动下载已取消，本机账本保持原样。', '自動取得を中止しました。ローカル台帳は変更されていません。', 'Automatic download cancelled. The local ledger is unchanged.'),
    ('本机有尚未同步的修改，已暂停自动下载；请先核对并上传或手动恢复。', '未同期の変更があるため自動取得を保留しました。確認後にアップロードするか、手動で復元してください。', 'Automatic download paused because local edits have not synced. Review and upload them, or restore manually.'),
    ('手机有离线待同步记录，已暂停自动下载；请先完成同步。', '端末に未送信の記録があるため自動取得を保留しました。先に同期してください。', 'Automatic download paused while this device has unsent entries. Sync them first.'),
    ('此账号正在下载最新云端账本，请稍后再试。', 'このアカウントの台帳を取得中です。しばらくしてから再試行してください。', 'This account is already downloading its ledger. Try again shortly.'),
    ('Agent 正在处理请求，已暂停自动下载，请稍后重试。', 'Agent が処理中のため自動取得を保留しました。後で再試行してください。', 'Automatic download paused while the Agent is working. Try again later.'),
    ('下载期间云端连接已改变，请重试。', '取得中にクラウド接続が変わりました。再試行してください。', 'The cloud connection changed during download. Try again.'),
    ('显示金额', '金額を表示', 'Show amounts'),
    ('隐藏金额', '金額を隠す', 'Hide amounts'),
    ('最小化', '最小化', 'Minimize'),
    ('最大化', '最大化', 'Maximize'),
    ('还原窗口', '元のサイズに戻す', 'Restore window'),
    ('关闭窗口', 'ウィンドウを閉じる', 'Close window'),

    ('记录', '記録', 'Record'),
    ('更多', 'その他', 'More'),
    ('预算', '予算', 'Budget'),
    ('本期支出', '今期の支出', 'Period spending'),
    ('本期收入', '今期の収入', 'Period income'),
    ('欠款估算', '債務の目安', 'Estimated debt'),
    ('搜索', '検索', 'Search'),
    ('管理账户', '口座を管理', 'Manage accounts'),
    ('报表', 'レポート', 'Reports'),
    ('全部', 'すべて', 'See all'),
    ('交易详情', '取引の詳細', 'Entry details'),

    ('总览', '概要', 'Overview'),
    ('生活，有迹可循', '暮らしを、ていねいに', 'A little more clarity'),
    ('总净资产 · JPY', '総純資産 · JPY', 'Total net assets · JPY'),
    ('当期纯利润 · JPY', '当期純利益 · JPY', 'Current net profit · JPY'),
    ('我的账本', 'マイ台帳', 'My ledger'),
    ('人民币资产独立核算', '人民元資産は別集計', 'CNY assets tracked separately'),
    ('人民币净利润', '人民元の純利益', 'CNY net profit'),
    ('汇率不全', '為替レート不足', 'incomplete exchange rates'),
    ('＋  记一笔', '＋ 記帳する', '＋ Record'),
    ('查看账户', '口座を見る', 'Accounts'),
    ('常用功能', 'よく使う機能', 'Favorites'),
    ('添加常用功能', 'お気に入りに追加', 'Add favorite'),
    ('移除此常用功能', 'このお気に入りを削除', 'Remove this favorite'),
    ('点击加号添加常用功能', '＋をクリックして機能を追加', 'Click + to add a favorite'),
    ('选择要固定在左侧的功能', '左側に固定する機能を選択', 'Choose features to pin on the left'),
    ('所有功能都已添加', 'すべての機能が追加されています', 'All features have been added'),
    ('无法保存常用功能', 'お気に入りを保存できません', 'Could not save favorites'),
    ('常用功能没有保存：{error}', 'お気に入りを保存できませんでした：{error}', 'Favorites were not saved: {error}'),
    ('无法保存界面布局', '画面レイアウトを保存できません', 'Could not save the interface layout'),
    ('侧边栏宽度没有保存：{error}', 'サイドバーの幅を保存できませんでした：{error}', 'Sidebar width was not saved: {error}'),
    ('固定资产管理', '固定資産管理', 'Fixed asset management'),
    ('确认删除：{target}？\n\n{impact}', '削除を確認します：「{target}」を削除しますか？\n\n{impact}', 'Confirm deletion: remove “{target}”?\n\n{impact}'),
    ('请确认此操作后重试。', 'この操作を確認してから再試行してください。', 'Confirm this action and try again.'),
    ('请确认恢复操作后重试。', '復元操作を確認してから再試行してください。', 'Confirm the restore operation and try again.'),
    ('预算，还剩', '予算の残り', 'Room in your budget'),
    ('钱花在哪里', '支出の内訳', 'Where it went'),
    ('最近记录', '最近の記録', 'Latest activity'),
    ('从第一笔开始记录生活', '最初の記帳から始めましょう', 'Start with your first entry'),
    ('含人民币参考汇率折算', '人民元の参考換算を含む', 'Includes CNY reference conversion'),
    ('记录后会在这里呈现', '記帳するとここに表示されます', 'Your spending will appear here'),
    ('账本暂时无法读取，请刷新重试。', '台帳を読み込めません。更新してください。', 'Could not read your ledger. Please refresh.'),
    ('● 本机账本', '● ローカル台帳', '● Local ledger'),
    ('备份与同步', 'バックアップと同期', 'Backup & sync'),
    ('查找记录', '記録を検索', 'Find entries'),
    ('管理账单', '取引を管理', 'Manage entries'),
    ('暂无记录', '記録がありません', 'No entries yet'),
    ('加载更多', 'さらに表示', 'Load more'),
    ('资金账户', '資金口座', 'Cash accounts'),
    ('账户与额度按本机账本计算', '残高と利用枠はローカル台帳から計算されます', 'Balances and limits are based on the local ledger'),
    ('管理信用卡', 'カードを管理', 'Manage credit cards'),
    ('欠款为额度差额估算，不代表当月账单。', '債務は利用枠の差額による目安で、当月請求額ではありません。', 'Debt is an estimate from credit availability, not the monthly bill.'),
    ('连接 GitHub / Gitee，上传与恢复数据', 'GitHub / Giteeに接続してデータを保存・復元', 'Connect GitHub / Gitee to upload and restore data'),
    ('设置与 Agent Skill', '設定・Agent Skill', 'Settings & agent skills'),
    ('管理服务、外观、语言和 Skill', 'API・外観・言語・Skillを管理', 'Manage services, appearance, language and skills'),
    ('重新打开当前软件', 'アプリを再度開きます', 'Reopen the application'),
    ('部分历史人民币记录缺少汇率，未计入合并报表。', '一部の過去の人民元取引は為替未登録のため合計に含まれません。', 'Some historical CNY entries lack exchange rates and are excluded from combined totals.'),

    ('外观', '外観', 'Appearance'),
    ('跟随系统', 'システム設定に従う', 'Follow system'),
    ('浅色模式', 'ライトモード', 'Light mode'),
    ('深色模式', 'ダークモード', 'Dark mode'),
    ('浅色、深色或跟随系统', 'ライト・ダーク・システム連動', 'Light, dark or follow system'),
    ('每一笔，都清楚。', '毎日の記録を、明確に。', 'Every entry, in clarity.'),
    ('记录日常，安心管理。', '日々を記録、安心して管理。', 'Your everyday finances, at ease.'),
    ('饮食回顾与健康建议', '食事の振り返りと健康アドバイス', 'Food reviews and wellness tips'),
    ('选择你喜欢的明暗外观。跟随系统会自动适应电脑的外观设置。', 'お好みの外観を選択してください。システム設定に従うと、PCの外観に自動的に合わせます。', 'Choose your appearance. Follow system automatically matches your computer.'),
    ('点击应用或确认后生效；取消不会改变当前外观。', '「適用」または「確定」で反映されます。キャンセルでは外観は変わりません。', 'Apply or Done saves the change. Cancel keeps the current appearance.'),

    ("工作空间", "ワークスペース", "Workspace"),
    ("财务管理", "家計管理", "Finances"),
    ("对话记账", "チャットで記帳", "Conversation"),
    ("重启软件", "アプリを再起動", "Restart app"),
    ("确认重启", "再起動の確認", "Confirm restart"),
    ("稍后重试", "後でもう一度お試しください", "Try again later"),
    ("重启失败", "再起動に失敗しました", "Restart failed"),
    ("记账或定期收支正在处理中，请等处理完成后再重启。", "記帳または定期収支を処理中です。完了してから再起動してください。", "A bookkeeping or recurring transaction is being processed. Wait until it finishes before restarting."),
    ("记账或定期收支正在处理中，请等处理完成后再从 GitHub 恢复。", "記帳または定期収支を処理中です。完了してからGitHubから復元してください。", "A bookkeeping or recurring transaction is being processed. Wait until it finishes before restoring from GitHub."),
    ("将重新打开软件并关闭当前窗口。当前对话、未发送文字、图片和待确认草稿会丢失；已保存的账本数据不受影响。继续吗？", "アプリを再度開き、現在のウィンドウを閉じます。現在の会話、未送信のテキストや画像、確認待ちの下書きは失われます。保存済みの台帳データには影響しません。続行しますか？", "The app will reopen and close this window. The current conversation, unsent text and images, and pending drafts will be lost. Saved ledger data will not be affected. Continue?"),
    ("无法启动新窗口：{error}", "新しいウィンドウを起動できません：{error}", "Could not start the new window: {error}"),
    ("新窗口未能保持运行；当前窗口仍然打开。请检查启动环境后重试。", "新しいウィンドウを起動できなかったため、現在のウィンドウを開いたままにしました。起動環境を確認して再試行してください。", "The new window did not stay open, so this window remains open. Check the launch environment and try again."),
    ("付款方式和定期付款", "支払方法と定期支払い", "Payment Methods & Recurring Payments"),
    ("管理支付规则与周期性收支", "支払ルールと定期収支を管理", "Manage payment rules and recurring transactions"),
    ("银行账户和信用卡", "銀行口座とクレジットカード", "Bank Accounts & Credit Cards"),
    ("查看账户余额、信用额度和还款", "口座残高、利用枠、返済を確認", "View account balances, credit limits, and repayments"),
    ("财务报表和预算", "財務諸表と予算", "Financial Statements & Budget"),
    ("查看家庭财务并管理分类预算", "家計レポートとカテゴリ別予算を管理", "View household finances and manage category budgets"),
    ("当前记账请求完成后再打开财务管理。", "現在の記帳リクエストが完了してから財務管理を開いてください。", "Open finance management after the current bookkeeping request finishes."),
    ("保存完成", "保存完了", "Saved"),
    ("标记已核对", "確認済みにする", "Mark reviewed"),
    ("无法读取账户", "口座を読み込めません", "Unable to read accounts"),
    ("账本中没有可用于入账的账户。", "記帳に使用できる口座が台帳にありません。", "No account is available for posting in this ledger."),
    ("无法核对", "確認できません", "Unable to review"),
    ("选择入账账户", "記帳口座を選択", "Choose posting account"),
    ("这条备查记录尚未绑定账户。请选择实际付款账户；确认后会转为已入账并影响账户余额。", "この参考記録には口座が割り当てられていません。実際の支払口座を選択してください。確定すると記帳済みになり、口座残高に反映されます。", "This memo entry has no account. Choose the account that was actually used; confirming will post it and affect the account balance."),
    ("入账账户", "記帳口座", "Posting account"),
    ("交易币种：{currency}；若账户币种不同，将按交易日参考汇率计算扣款金额。", "取引通貨：{currency}。口座通貨が異なる場合、取引日の参考為替レートで引落額を計算します。", "Transaction currency: {currency}. If the account uses another currency, its debit will be calculated with the transaction-date reference rate."),
    ("继续核对", "確認を続ける", "Continue review"),
    ("请选择一个有效的入账账户。", "有効な記帳口座を選択してください。", "Choose a valid posting account."),
    ("备查流水会转为已入账，并从所选账户扣款或增加余额。", "参考記録は記帳済みに変更され、選択した口座の残高が支出または収入分だけ更新されます。", "The memo entry will be posted and the selected account balance will be reduced or increased."),
    ("流水会保留现有账户，只清除待核对状态。", "現在の口座を維持し、要確認の状態だけを解除します。", "The existing account will be kept; only the review flag will be cleared."),
    ("确认将流水 #{id} 标记为已核对？\n{description}\n账户：{account}\n{impact}", "取引 #{id} を確認済みにしますか？\n{description}\n口座：{account}\n{impact}", "Mark entry #{id} as reviewed?\n{description}\nAccount: {account}\n{impact}"),
    ("确认核对", "確認を確定", "Confirm review"),
    ("核对失败", "確認に失敗しました", "Review failed"),
    ("备查流水已转为已入账。", "参考記録を記帳済みに変更しました。", "The memo entry has been posted."),
    ("原已入账流水的待核对标记已清除。", "記帳済み取引の要確認マークを解除しました。", "The review flag has been cleared from the posted entry."),
    ("核对完成", "確認完了", "Review complete"),
    ("流水 #{id} 已核对。{detail}", "取引 #{id} を確認しました。{detail}", "Entry #{id} reviewed. {detail}"),
    ("找不到所选账务记录。", "選択した取引が見つかりません。", "The selected ledger entry was not found."),
    ("所选流水已不需要核对。", "選択した取引は確認不要になっています。", "The selected entry no longer needs review."),
    ("只有收入或支出备查流水可以在核对时转为已入账。", "確認時に記帳済みに変更できるのは、収入または支出の参考記録のみです。", "Only memo-only income or expense entries can be posted during review."),
    ("备查流水转为已入账前必须选择实际账户。", "参考記録を記帳済みにする前に、実際の口座を選択してください。", "Choose the actual account before posting a memo entry."),
    ("请选择银行、钱包、券/预付、交通卡或信用卡账户。", "銀行、ウォレット、プリペイド、交通系IC、またはクレジットカード口座を選択してください。", "Choose a bank, wallet, prepaid, transit, or credit card account."),
    ("交易日期早于账户期初日期：{date}", "取引日が口座の開始日より前です：{date}", "The transaction date is earlier than the account opening date: {date}"),
    ("账户换算汇率有效日期不能晚于交易日期", "口座換算レートの適用日は取引日より後にできません", "The account conversion rate date cannot be later than the transaction date"),
    ("按交易日参考汇率换算后的账户扣款金额小于最小货币单位。", "取引日の参考為替レートで換算した口座引落額が最小通貨単位を下回っています。", "The converted account debit is below the smallest currency unit."),
    ("流水状态已改变，请刷新后重试。", "取引の状態が変更されています。更新してから再試行してください。", "The entry changed; refresh and try again."),
    ("图片记账草稿（尚未入账）", "画像からの記帳案（未記帳）", "Image entry draft (not saved)"),
    ("未提供模型名称", "モデル名不明", "Model name unavailable"),
    ("未识别，请按票面核对", "未認識。レシートを確認してください", "Not recognized; check the receipt"),
    ("识别模型：{model}", "認識モデル：{model}", "Recognition model: {model}"),
    ("商家：{value}", "店舗：{value}", "Merchant: {value}"),
    ("日期：{value}", "日付：{value}", "Date: {value}"),
    ("金额：{amount} {currency}", "金額：{amount} {currency}", "Amount: {amount} {currency}"),
    ("类别：{value}", "分類：{value}", "Category: {value}"),
    ("账户：{value}", "口座：{value}", "Account: {value}"),
    ("商品/说明：{value}", "商品・説明：{value}", "Items / description: {value}"),
    ("备查，不影响账户余额", "参考記録（口座残高に影響なし）", "Memo only; no effect on account balance"),
    ("账户按已保存规则选择，请核对实际付款账户。", "保存済みルールで口座を選びました。実際の支払口座を確認してください。", "Account selected by saved rules; check the actual payment account."),
    ("金额核对：票面小计、税额及折扣与合计一致。", "金額確認：小計・税額・値引きと合計が一致しています。", "Amount check: subtotal, tax and discounts agree with the total."),
    ("金额核对：票面小计、税额及折扣与合计不一致，请核对并修正。", "金額確認：小計・税額・値引きと合計が一致しません。確認して修正してください。", "Amount check: subtotal, tax and discounts do not agree with the total. Check and correct it."),
    ("金额核对：缺少可计算的票面字段，请核对最终实付总额。", "金額確認：計算に必要な情報が不足しています。最終支払総額を確認してください。", "Amount check: insufficient receipt fields for arithmetic verification. Check the final paid total."),
    ("金额已按你的修改更新，请重新核对。", "指定どおり金額を修正しました。再確認してください。", "Amount updated as requested; check the revised draft."),
    ("疑似重复：同日期、账户和金额已有流水 {ids}，请核对。", "重複の可能性：同じ日付・口座・金額の取引 {ids} があります。確認してください。", "Possible duplicate: entries {ids} have the same date, account and amount. Please check."),
    ("请核对图片后回复“确认记账”；有误请说明要修改的字段，或回复“取消这笔”。", "画像と照合し「記帳を確定」と返信してください。誤りがあれば修正箇所を入力するか、「取消这笔」で取り消せます。", "Check the image and reply 'confirm entry'. Describe any corrections, or reply 'cancel' to discard the draft."),
    ("已有待确认的图片记账草稿。请先确认记账、修改草稿或取消这笔，再提交新图片。", "確認待ちの記帳案があります。確定・修正・取消を行ってから、新しい画像を送信してください。", "An image draft is awaiting review. Confirm, edit or cancel it before sending another image."),
    ("记账尚未完成", "記帳が完了していません", "Entry not completed"),
    ("当前记账尚未完成，后续消息继续使用 {service}（{model}）。确认或取消后才能切换 Agent 或 API 服务。", "記帳が完了するまで、後続メッセージも{service}（{model}）を使用します。確定または取消の後にAgentやAPIサービスを切り替えられます。", "This entry is still in progress. Follow-up messages will keep using {service} ({model}). You can switch agents or API services after confirming or canceling it."),
    ("正在处理图片，服务：{service}；模型：{model}……", "画像処理中。サービス：{service}、モデル：{model}……", "Processing image; service: {service}; model: {model}…"),
    ("家庭记账", "家計簿", "Household Bookkeeping"),
    ("助手", "アシスタント", "Assistant"),
    ("你", "あなた", "You"),
    ("你好，直接告诉我一笔收入、消费、转账或还款。信息不够时我会先追问，确认后才写入本地账本。", "こんにちは。収入、支出、振替、返済を入力してください。不足している情報があれば確認してから、ローカル台帳に記帳します。", "Hi. Enter income, an expense, transfer, or repayment. I’ll ask for any missing details before writing it to the local ledger."),
    ("我会先检索本地近期饮食记录，再交给饮食健康 Agent 单独配置的模型和 Skill 给出均衡饮食建议。记录不足时会说明限制；此模式不会修改记录。", "まずローカルの最近の食事記録を検索し、食事と健康Agent専用のモデルとSkillでバランスのよい食事を提案します。記録が不十分な場合はその旨を説明します。このモードでは記録を変更しません。", "I’ll search recent local food records, then use the Food & Health agent’s assigned model and Skill to suggest balanced meals. I’ll explain when records are limited. This mode does not change records."),
    ("⚙  设置", "⚙  設定", "⚙  Settings"),
    ("设置", "設定", "Settings"),
    ("管理服务、解析和数据", "サービス、解析、データを管理", "Manage services, parsing, and data"),
    ("▤  更多功能  ▾", "▤  その他の機能  ▾", "▤  More Features  ▾"),
    ("自然语言输入 · 本地 SQLite 账本 · 账务信息由 API 解析", "自然言語入力 · ローカルSQLite台帳 · 取引情報はAPIで解析", "Natural language entry · Local SQLite ledger · Transactions parsed by API"),
    ("选择 Agent", "Agentを選択", "Select agent"),
    ("纯文字", "テキスト", "Text"),
    ("识图", "画像認識", "Image"),
    ("含图片", "画像付き", "With image"),
    ("纯文字 API 服务", "テキスト用APIサービス", "Text API service"),
    ("含图片 API 服务", "画像対応APIサービス", "Image API service"),
    ("只读本地记录", "ローカル記録のみ参照", "Reads local records only"),
    ("本地 SQLite 账本", "ローカルSQLite台帳", "Local SQLite ledger"),
    ("为每个 Agent 分别选择纯文字服务和含图片服务。发送时程序会按当前消息是否附图自动路由；含图片服务必须支持视觉输入。两个 Agent 的设置和 Skill 仍彼此独立。", "Agentごとにテキスト用と画像対応のAPIサービスを選択します。送信時に添付画像の有無で自動的に振り分けます。画像対応サービスは画像入力をサポートしている必要があります。2つのAgentの設定とSkillはそれぞれ独立しています。", "Choose separate text and image API services for each agent. Requests are routed based on whether the current message includes an image. The image service must support image input. Each agent keeps its own settings and Skill."),
    ("纯文字服务已切换；该 Agent 的对话上下文已清空。", "テキスト用サービスを切り替えました。このAgentの会話コンテキストを消去しました。", "Text service changed; this agent's conversation context was cleared."),
    ("含图片服务已切换；该 Agent 的对话上下文已清空。", "画像対応サービスを切り替えました。このAgentの会話コンテキストを消去しました。", "Image service changed; this agent's conversation context was cleared."),
    ("文字", "テキスト", "Text"),
    ("记账", "家計簿", "Bookkeeping"),
    ("饮食健康", "食事と健康", "Food & Health"),
    ("＋ 添加图片", "＋ 画像を追加", "+ Add image"),
    ("发送记账", "送信して記帳", "Send entry"),
    ("发送饮食咨询", "食事の相談を送信", "Send food question"),
    ("重置对话", "会話をリセット", "Reset conversation"),
    ("当前对话已重置，可以开始新的测试。", "現在の会話をリセットしました。新しいテストを開始できます。", "Conversation reset. You can start a new test."),
    ("可拖入 JPG/PNG/WebP 图片到输入框或附件栏", "JPG/PNG/WebP画像を入力欄または添付欄にドロップできます", "Drop JPG/PNG/WebP images into the input box or attachment area"),
    ("可拖入食物图片；记录与饮食 Skill 会发给饮食 Agent 的模型", "食品画像をドロップできます。記録と食事Skillは食事Agentのモデルに送信されます", "Drop food images here. Food records and the Food Skill are sent to the Food agent's model."),
    ("自然语言输入", "自然言語入力", "Natural language input"),
    ("发送", "送信", "Send"),
    ("添加图片", "画像を追加", "Add image"),
    ("支持的图片", "対応画像", "Supported images"),
    ("选择食物或收据图片", "食品またはレシート画像を選択", "Select food or receipt images"),
    ("饮食健康 Agent 会检索本地饮食回顾，并将记录摘要、此 Agent 单独选择的 Skill 正文和本轮问题发送给当前消息对应的服务；附图消息使用含图片服务，纯文字消息使用纯文字服务。本机 Ollama 留在本机，远程服务会收到这些内容。此模式只提供饮食建议，不会写入记录。Enter 换行，Ctrl+Enter 发送。", "食事と健康Agentはローカルの食事記録を検索し、記録の要約、このAgent専用のSkill本文、今回の質問を現在のメッセージに対応するサービスへ送信します。画像付きのメッセージには画像対応サービスを、テキストのみのメッセージにはテキスト用サービスを使います。本機のOllamaは本機内で処理され、リモートサービスにはこれらの情報が送信されます。このモードは食事の提案のみを行い、記録は変更しません。Enterで改行、Ctrl+Enterで送信。", "The Food & Health agent searches local food records and sends a summary, its assigned Skill, and your question to the service selected for this message. Messages with images use the image service; text-only messages use the text service. Ollama runs locally; remote services receive this information. This mode gives food suggestions and does not write records. Enter adds a line; Ctrl+Enter sends."),
    ("正在加载，等待 API 回复……", "読み込み中。APIの応答を待っています……", "Loading; waiting for the API response…"),
    ("中断任务", "タスクを中断", "Interrupt task"),
    ("正在中断……", "中断しています……", "Interrupting…"),
    ("正在强制中断任务……", "タスクを強制終了しています……", "Force-stopping the task…"),
    ("请求已完成，正在安全保存账本结果……", "リクエストが完了しました。台帳へ安全に保存しています……", "Request finished; safely saving the ledger result…"),
    ("任务已中断，本次结果未写入本地账本。服务商可能已收到请求并继续处理。", "タスクを中断しました。今回の結果はローカル台帳に保存されていません。サービス提供者はリクエストを受信し、処理を続けている場合があります。", "Task interrupted. This result was not written to the local ledger. The provider may already have received the request and may continue processing it."),
    ("任务已中断，本次结果未写入本地账本。", "タスクを中断しました。今回の結果はローカル台帳に保存されていません。", "Task interrupted. This result was not written to the local ledger."),
    ("正在处理到期的定期收支，请稍后再发送。", "期限到来した定期収支を処理中です。しばらくしてから送信してください。", "Due recurring entries are being processed. Please send again shortly."),
    ("后台任务无法启动：{error}", "バックグラウンドタスクを開始できません：{error}", "Could not start the background task: {error}"),
    ("后台任务意外退出，本次结果未写入账本。请重试。", "バックグラウンドタスクが予期せず終了しました。今回の結果は台帳に保存されていません。再試行してください。", "The background task exited unexpectedly. This result was not written to the ledger. Please try again."),
    ("程序暂时无法完成请求。请检查账本文件和 API 配置后重试。", "リクエストを完了できませんでした。台帳ファイルとAPI設定を確認して再試行してください。", "The request could not be completed. Check the ledger file and API settings, then try again."),
    ("请求期间账本结构发生变化，本次结果没有写入。请重新打开软件后重试。", "リクエスト中に台帳構造が変更されたため、今回の結果は保存されていません。ソフトウェアを再起動して再試行してください。", "The ledger structure changed during the request, so this result was not saved. Reopen the app and try again."),
    ("请求期间账本已有其他变更，本次结果没有写入。请核对账本后重试。", "リクエスト中に台帳が別途変更されたため、今回の結果は保存されていません。台帳を確認して再試行してください。", "The ledger changed during the request, so this result was not saved. Review the ledger and try again."),
    ("请求结果尝试删除已有账本数据，本次结果没有写入。", "リクエスト結果が既存の台帳データを削除しようとしたため、保存されていません。", "The request result attempted to delete existing ledger data and was not saved."),
    ("请求结果尝试改写已有账本数据，本次结果没有写入。", "リクエスト結果が既存の台帳データを書き換えようとしたため、保存されていません。", "The request result attempted to alter existing ledger data and was not saved."),
    ("请求结果包含不支持的账本变更（{table}），本次结果没有写入。", "リクエスト結果に未対応の台帳変更（{table}）が含まれているため、保存されていません。", "The request result contains an unsupported ledger change ({table}) and was not saved."),
    ("账本关联校验未通过，本次结果没有写入。", "台帳の関連整合性チェックに失敗したため、今回の結果は保存されていません。", "Ledger relationship validation failed, so this result was not saved."),
    ("请求副本不存在，本次结果没有写入账本。", "リクエスト用の複製が見つからないため、今回の結果は台帳に保存されていません。", "The request copy is missing, so this result was not written to the ledger."),
    ("正在等待 API", "APIの応答待ち", "Waiting for API"),
    ("正在记账", "記帳中", "Saving entry"),
    ("正在读取账本…", "台帳を読み込んでいます…", "Loading ledger…"),
    ("读取失败。", "読み込みに失敗しました。", "Could not load data."),
    ("Enter 换行，Ctrl+Enter 发送。", "Enterで改行、Ctrl+Enterで送信。", "Enter adds a line; Ctrl+Enter sends."),
    ("关闭", "閉じる", "Close"),
    ("保存", "保存", "Save"),
    ("确认", "確定", "OK"),
    ("应用", "適用", "Apply"),
    ("设置已保存并应用。", "設定を保存して適用しました。", "Settings saved and applied."),
    ("取消", "キャンセル", "Cancel"),
    ("刷新", "更新", "Refresh"),
    ("删除", "削除", "Delete"),
    ("删除当前", "現在の項目を削除", "Delete selected"),
    ("重新读取", "再読み込み", "Reload"),
    ("卸载 Skill", "Skillを解除", "Unload Skill"),
    ("＋ 新建服务", "＋ サービスを追加", "+ Add service"),
    ("＋ 新增定期收支", "＋ 定期収支を追加", "+ Add recurring item"),
    ("编辑规则", "ルールを編集", "Edit rule"),
    ("＋ 添加账户", "＋ 口座を追加", "+ Add account"),
    ("＋ 新增信用卡", "＋ クレジットカードを追加", "+ Add credit card"),
    ("＋ 添加支付方式", "＋ 支払ルールを追加", "+ Add payment rule"),
    ("保存账户", "口座を保存", "Save account"),
    ("保存信用卡", "カードを保存", "Save card"),
    ("保存快照", "スナップショットを保存", "Save snapshot"),
    ("保存计划", "計画を保存", "Save plan"),
    ("保存还款", "返済を保存", "Save repayment"),
    ("保存或取消余额调整后再删除账户。", "残高調整を保存またはキャンセルしてから口座を削除してください。", "Save or cancel the balance adjustment before deleting an account."),
    ("调整差额", "差額を調整", "Adjust balance"),
    ("确认调整并记账", "調整して記帳", "Apply adjustment and post entry"),
    ("确认调整（不记账）", "調整を確認（記帳しない）", "Apply adjustment without posting"),
    ("将差额记入账本", "差額を台帳に記帳", "Post the difference to the ledger"),
    ("记录还款", "返済を記録", "Record repayment"),
    ("记录信用卡还款", "クレジットカードの返済を記録", "Record credit card repayment"),
    ("录入额度快照", "利用枠スナップショットを入力", "Enter credit limit snapshot"),
    ("每月应还计划", "毎月の返済予定", "Monthly repayment plan"),
    ("设置每月应还计划", "毎月の返済予定を設定", "Set monthly repayment plan"),
    ("暂停/恢复计划", "予定を一時停止／再開", "Pause or resume plan"),
    ("暂停 / 启用", "一時停止／有効化", "Pause / enable"),
    ("排序：", "並び順：", "Sort:"),
    ("默认排序", "既定の順序", "Default order"),
    ("按币种", "通貨別", "By currency"),
    ("所有账户余额和积分格已解锁。将数值改成实际余额/积分；留空项目不变。勾选“将差额记入账本”会新增盘盈/盘亏流水；取消时已建账户只更新余额快照，首次盘点只建立期初余额。", "すべての口座残高とポイント欄を編集できます。実際の残高/ポイント数を入力してください。空欄は変更されません。「差額を台帳に記帳」を選ぶと過不足の取引を追加します。選択しない場合、既存口座は残高スナップショットのみ更新し、初回棚卸しは開始残高を設定します。", "All balance and points fields are editable. Enter the counted values; blank fields are unchanged. Posting the difference adds an overage/shortage entry. If unchecked, existing accounts update only their balance snapshot; the first count sets the opening balance."),
    ("账面余额已载入", "台帳残高を読み込み済み", "Ledger balance loaded"),
    ("积分余额已载入", "ポイント残高を読み込み済み", "Points balance loaded"),
    ("包含推算期初", "推算した開始残高を含む", "Includes inferred opening balance"),
    ("记录不完整", "記録が不完全", "Incomplete records"),
    ("等待首次盘点", "初回棚卸し待ち", "Waiting for first count"),
    ("输入实际余额", "実際の残高を入力", "Enter actual balance"),
    ("已取消调整；账本未变更。", "調整をキャンセルしました。台帳は変更されていません。", "Adjustment cancelled; the ledger was not changed."),
    ("与账面一致，没有新增分录。", "台帳残高と一致しています。仕訳は追加されていません。", "Matches the ledger; no entry was added."),
    ("余额调整完成", "残高調整が完了しました", "Balance adjustment complete"),
    ("调整已保存。", "調整を保存しました。", "Adjustment saved."),
    ("现金管理", "現金管理", "Cash management"),
    ("现金管理表", "現金管理表", "Cash balances"),
    ("隐藏数字", "数字を隠す", "Hide numbers"),
    ("显示数字", "数字を表示", "Show numbers"),
    ("请先显示数字", "先に数字を表示してください", "Show numbers first"),
    ("点击“显示数字”后再调整账户余额。", "「数字を表示」をクリックしてから口座残高を調整してください。", "Click “Show numbers” before adjusting account balances."),
    ("查看和调整现金、钱包及积分余额", "現金、ウォレット、ポイント残高を確認・調整", "View and adjust cash, wallet, and points balances"),
    ("表内显示非信用卡资金账户和积分；余额平时只读。可新增银行、钱包、券/预付、交通卡或积分账户。未关联流水或计划的账户可删除，删除前会自动备份并确认一次。信用卡单独管理，不计入现金表。", "この表にはクレジットカード以外の資金口座とポイントを表示します。通常、残高は読み取り専用です。銀行、ウォレット、プリペイド、交通系IC、ポイント口座を追加できます。取引や予定に使われていない口座は削除できます。削除前に自動バックアップと1回の確認を行います。クレジットカードは別管理です。", "Shows non-credit-card accounts and points. Balances are read-only until adjusted. Add bank, wallet, prepaid, transit, or points accounts. Unused accounts can be deleted after an automatic backup and one confirmation. Credit cards are managed separately."),
    ("添加资金账户", "資金口座を追加", "Add funds account"),
    ("信用卡不属于现金管理表；此处新增账户只建立期初余额，不会自动生成收支。", "クレジットカードは現金管理表に含まれません。ここで追加する口座は開始残高のみを設定し、収入や支出は自動作成しません。", "Credit cards are not shown in cash management. Adding an account here sets its opening balance only; no income or expense is created."),
    ("确认调整（不记账）", "調整を確認（記帳しない）", "Apply adjustment without posting"),
    ("添加资金账户", "資金口座を追加", "Add funds account"),
    ("信用卡管理", "クレジットカード管理", "Credit card management"),
    ("额度快照、还款与每月计划", "利用枠スナップショット、返済、月次予定", "Limit snapshots, repayments, and monthly plans"),
    ("当前欠款估算 = 总额度 − 当前可用额度。可用额度从手工快照按账内消费、退款和还款更新。还款只记账户间转账。每张卡固定扣款账户和还款日；本期金额需要每月填写，空白不记账、下月不沿用。计划只会写入本地账本，不会操作银行扣款。", "現在の債務目安 = 利用限度額 − 現在の利用可能額。利用可能額は手入力のスナップショットを基準に、台帳の利用・返金・返済から更新します。返済は口座間振替として記録します。カードごとに引落口座と返済日を固定し、当月の金額は毎月入力します。空欄なら記帳せず、翌月へ引き継ぎません。予定はローカル台帳に記録するだけで、銀行から引き落としません。", "Estimated debt = total limit − available credit. Available credit starts from a manual snapshot and is updated using ledger purchases, refunds, and repayments. Repayments are transfers. Each card has a fixed payment account and due date; enter the amount each month. Blank amounts are not posted and never carry forward. Plans only write to the local ledger and do not debit a bank."),
    ("还款需要明确选择转出账户和信用卡。提交后只记账户间转账，不增加消费；额度快照仍以你重新录入的卡片应用数值为准。", "返済時は振替元口座とクレジットカードを選択してください。保存すると口座間振替だけを記録し、支出は増やしません。利用枠はカードアプリから再入力したスナップショットを基準にします。", "Select the source account and credit card. Saving records a transfer only; it does not add an expense. Credit limits remain based on the snapshot you enter from the card app."),
    ("按信用卡应用当前显示值录入。每张卡每天只保存一条快照；当前欠款估算将按总额度减可用额度计算，不等于当月账单。", "カードアプリに表示された現在の値を入力してください。各カードのスナップショットは1日1件保存します。債務目安は利用限度額から利用可能額を引いて計算し、当月の請求額を示すものではありません。", "Enter the values currently shown in the card app. One snapshot per card per day is saved. Estimated debt is total limit minus available credit; it is not the current bill."),
    ("信用卡、扣款账户和还款日按月固定；本期金额需要每个月重新填写，留空就不会自动记账，也不会沿用上个月金额。到期日当天程序运行且余额足够时，只在本地账本记转账，不会从银行实际扣款。错过日期或已有部分还款时不会自动补记。", "カード、引落口座、返済日は毎月固定です。当月金額は毎月入力してください。空欄なら記帳せず、前月の金額も引き継ぎません。返済日にプログラムが起動しており残高が十分な場合、ローカル台帳に振替を記録するだけで、銀行から実際に引き落とすことはありません。期限を過ぎた場合や一部返済がある場合、自動で差額を補いません。", "The card, payment account, and due date stay fixed each month. Enter the amount for each period; blank amounts are not posted and last month's amount is not reused. If the app runs on the due date and funds are sufficient, it records a local transfer only and does not debit the bank. Missed dates and partial repayments are not automatically reconciled."),
    ("新增信用卡", "クレジットカードを追加", "Add credit card"),
    ("这里只登记信用卡账户。额度与可用额度需另录快照；未知历史卡债不要猜，期初可填0并标为记录不完整。", "ここではクレジットカード口座を登録します。利用限度額と利用可能額は別途スナップショットで入力します。不明な過去の債務は推測せず、開始残高を0にして記録不完全と表示できます。", "Register the credit card account here. Enter its limit and available credit in a separate snapshot. Do not guess unknown past debt; use an opening balance of 0 and mark records incomplete."),
    ("信用卡名称", "カード名", "Card name"),
    ("总额度", "利用限度額", "Total limit"),
    ("当前可用额度", "現在の利用可能額", "Available credit"),
    ("当前欠款估算", "現在の債務目安", "Estimated debt"),
    ("最近信用卡还款", "最近のカード返済", "Recent card repayments"),
    ("下次还款日", "次回返済日", "Next due date"),
    ("下次还款日（以后每月同日）", "次回返済日（以後、毎月同日）", "Next due date (same day each month)"),
    ("本期金额", "当月金額", "Current period amount"),
    ("本期未填写", "当月未入力", "Not entered for this period"),
    ("信用卡还款", "クレジットカード返済", "Credit card repayment"),
    ("账面净债务", "台帳上の純債務", "Net debt on ledger"),
    ("家庭财务报表", "家計財務レポート", "Household financial report"),
    ("查看资产负债和本期收支", "資産・負債と当期収支を表示", "View assets, liabilities, and current-period income and expenses"),
    ("家庭财务报表", "家計財務レポート", "Household financial report"),
    ("资产负债表", "貸借対照表", "Balance sheet"),
    ("本期利润表", "当期損益計算書", "Current-period income statement"),
    ("资产负债表按 JPY、积分、CNY 分开展示；利润表按每月15日至次月14日统计。原币金额保留，人民币另按交易日参考汇率折算为日元汇总。", "貸借対照表はJPY・ポイント・CNYを分けて表示します。損益計算書は毎月15日から翌月14日までを集計します。原通貨を保持し、人民元は取引日の参考レートで円換算した合計も表示します。", "The balance sheet separates JPY, points, and CNY. The income statement covers the 15th through the 14th. Original amounts are preserved; CNY is also converted to JPY using the transaction-date reference rate."),
    ("刷新报表", "レポートを更新", "Refresh report"),
    ("报表已按账本最新记录刷新。", "最新の台帳データでレポートを更新しました。", "Report refreshed from the latest ledger data."),
    ("项目", "項目", "Item"),
    ("金额", "金額", "Amount"),
    ("币种/单位", "通貨／単位", "Currency / unit"),
    ("说明", "説明", "Notes"),
    ("收入合计", "収入合計", "Total income"),
    ("消费合计", "支出合計", "Total expenses"),
    ("其中：已入账消费", "うち記帳済み支出", "Of which: posted expenses"),
    ("其中：仅备查消费", "うち参考記録のみ", "Of which: memo-only expenses"),
    ("待核对消费", "要確認の支出", "Expenses to review"),
    ("支出分类：", "支出分類：", "Expense category: "),
    ("本期合计", "当期合計", "Period total"),
    ("已记录收入", "記録済み収入", "Recorded income"),
    ("包含已入账与备查支出", "記帳済みと参考記録の支出を含む", "Includes posted and memo-only expenses"),
    ("会影响账户余额", "口座残高に反映", "Affects account balance"),
    ("不影响任何账户余额", "どの口座残高にも影響しません", "Does not affect any account balance"),
    ("包含在消费合计中，请核实", "支出合計に含まれます。確認してください", "Included in total expenses; please review"),
    ("按账本分类汇总", "台帳の分類別合計", "Grouped by ledger category"),
    ("收入减消费；备查消费也计入", "収入から支出を差し引いた額（参考記録を含む）", "Income minus expenses, including memo-only expenses"),
    ("JPY原币收入 + CNY按交易日汇率折算", "JPY収入 + 取引日レートで換算したCNY", "JPY income + CNY converted at the transaction-date rate"),
    ("JPY原币消费 + CNY按交易日汇率折算", "JPY支出 + 取引日レートで換算したCNY", "JPY expenses + CNY converted at the transaction-date rate"),
    ("含人民币交易日汇率折算", "取引日レートによるCNY換算を含む", "Includes CNY converted at the transaction-date rate"),
    ("全部已折算收支相抵", "換算済み収支の差引", "All converted income minus expenses"),
    ("待补汇率", "換算レート要確認", "Exchange rate needed"),
    ("未折算流水", "未換算の取引", "Unconverted transactions"),
    ("不计入JPY合并口径；需补充历史汇率", "JPY合算には含まれません。過去のレートが必要です", "Excluded from the JPY total; a historical exchange rate is needed"),
    ("银行存款仅统计银行账户。", "銀行預金は銀行口座のみを集計します。", "Bank deposits include bank accounts only."),
    ("净资产（已计负债）", "純資産（負債控除後）", "Net assets (after liabilities)"),
    ("货币资产", "貨幣資産", "Monetary assets"),
    ("资产合计", "資産合計", "Total assets"),
    ("负债合计", "負債合計", "Total liabilities"),
    ("负债小计", "負債小計", "Liabilities subtotal"),
    ("已确认负债", "確認済み負債", "Confirmed liabilities"),
    ("信用卡负债估算", "クレジットカード負債の推定", "Estimated credit card liabilities"),
    ("负债（待录入额度）", "負債（利用枠未入力）", "Liabilities (credit limit not entered)"),
    ("积分（单独展示，不计入资产）", "ポイント（別表示、資産に含めない）", "Points (shown separately, excluded from assets)"),
    ("非货币资产", "非貨幣資産", "Non-monetary assets"),
    ("其他非货币资产", "その他の非貨幣資産", "Other non-monetary assets"),
    ("待核对负余额（未计入资产合计）", "要確認のマイナス残高（資産合計から除外）", "Negative balances to review (excluded from total assets)"),
    ("积分负数（待核对）", "ポイント残高がマイナス（要確認）", "Negative points balance (review required)"),
    ("负余额（待核对）", "マイナス残高（要確認）", "Negative balance (review required)"),
    ("非货币负数（待核对）", "非貨幣残高がマイナス（要確認）", "Negative non-monetary balance (review required)"),
    ("未估算信用卡负债", "未推定のカード負債", "Credit card liability not estimated"),
    ("未生效账户", "未適用の口座", "Inactive account"),
    ("其他/尚未生效项目", "その他／未適用の項目", "Other / inactive items"),
    ("积分余额 ", "ポイント残高 ", "Points balance "),
    ("截至 ", "基準日 ", "As of "),
    ("统计截至 ", "集計基準日 ", "Through "),
    ("本期：", "当期：", "Period: "),
    ("信用卡欠款估算：", "カード債務の目安：", "Estimated card debt: "),
    ("全部货币资产：", "全貨幣資産：", "All monetary assets: "),
    ("已确认账面负债：", "確認済み台帳負債：", "Confirmed ledger liabilities: "),
    ("当前银行存款：", "現在の銀行預金：", "Current bank deposits: "),
    ("现金（日元）", "現金（日本円）", "Cash (JPY)"),
    ("现金（人民币）", "現金（人民元）", "Cash (CNY)"),
    ("资产（信用卡贷余）", "資産（カード利用可能枠）", "Assets (available credit)"),
    ("账户（币种）", "口座（通貨）", "Account (currency)"),
    ("转出账户", "振替元口座", "Source account"),
    ("扣款账户", "引落口座", "Payment account"),
    ("还款日期", "返済日", "Repayment date"),
    ("还款金额", "返済額", "Repayment amount"),
    ("金额单位：", "金額単位：", "Amount unit: "),
    ("还款金额单位：", "返済額の単位：", "Repayment unit: "),
    ("本期应还金额（每月重新填写）", "当月返済額（毎月入力）", "Amount due this period (enter each month)"),
    ("账单币种", "請求通貨", "Bill currency"),
    ("账单金额（", "請求額（", "Bill amount ("),
    ("账单金额→扣款币种", "請求額 → 引落通貨", "Bill amount → payment currency"),
    ("首次日期（支持202608、8月）", "初回日（202608、8月などに対応）", "First date (e.g. 202608 or 2026/8/1)"),
    ("期初日期", "開始日", "Opening date"),
    ("快照日期", "スナップショット日", "Snapshot date"),
    ("金额单位：请选择信用卡", "金額単位：クレジットカードを選択してください", "Amount unit: select a credit card"),
    ("每月应还日期", "毎月の返済日", "Monthly due date"),
    ("账户名称", "口座名", "Account name"),
    ("账户类型", "口座種別", "Account type"),
    ("余额完整度", "残高データの状態", "Balance data status"),
    ("期初余额/点数", "開始残高／ポイント", "Opening balance / points"),
    ("备注", "メモ", "Note"),
    ("日期", "日付", "Date"),
    ("餐次", "食事", "Meal"),
    ("吃了什么", "食べたもの", "Food eaten"),
    ("数量", "数量", "Quantity"),
    ("数量/单位（可选）", "数量／単位（任意）", "Quantity / unit (optional)"),
    ("商品/食材名称", "商品／食材名", "Item / ingredient"),
    ("商品/食材", "商品／食材", "Item / ingredient"),
    ("来源", "出典", "Source"),
    ("账本流水", "台帳取引", "Ledger entry"),
    ("分类", "分類", "Category"),
    ("操作", "操作", "Actions"),
    ("状态", "状態", "Status"),
    ("复制文字", "テキストをコピー", "Copy text"),
    ("复制选中内容", "選択範囲をコピー", "Copy selection"),
    ("复制全部文字", "すべてのテキストをコピー", "Copy all text"),
    ("复制选中行", "選択行をコピー", "Copy selected rows"),
    ("撤销", "元に戻す", "Undo"),
    ("重做", "やり直し", "Redo"),
    ("剪切", "切り取り", "Cut"),
    ("复制", "コピー", "Copy"),
    ("粘贴", "貼り付け", "Paste"),
    ("全选", "すべて選択", "Select all"),
    ("取消全选", "すべて選択解除", "Clear all"),
    ("更改将在点击应用或确认后保存。", "変更は「適用」または「確定」をクリックした後に保存されます。", "Changes will be saved when you click Apply or Confirm."),
    ("设置已保存。", "設定を保存しました。", "Settings saved."),
    ("有未保存的 API 服务更改；点击应用或确认后保存。", "未保存のAPIサービス変更があります。「適用」または「確定」をクリックして保存してください。", "There are unsaved API service changes. Click Apply or Confirm to save them."),
    ("API 服务更改尚未保存；点击应用或确认后生效。", "APIサービスの変更は未保存です。「適用」または「確定」をクリックして適用してください。", "API service changes are unsaved. Click Apply or Confirm to apply them."),
    ("已切换 API 服务草稿；点击应用或确认后保存。", "APIサービスの下書きを切り替えました。「適用」または「確定」をクリックして保存してください。", "Switched the API service draft. Click Apply or Confirm to save it."),
    ("新服务已创建为草稿；点击应用或确认后保存。", "新しいサービスを下書きとして作成しました。「適用」または「確定」をクリックして保存してください。", "The new service is a draft. Click Apply or Confirm to save it."),
    ("API 服务已从草稿移除；点击应用或确认后保存。", "APIサービスを下書きから削除しました。「適用」または「確定」をクリックして保存してください。", "The API service was removed from the draft. Click Apply or Confirm to save the change."),
    ("纯文字服务已更改，点击应用或确认后保存。", "テキスト用サービスを変更しました。「適用」または「確定」をクリックして保存してください。", "The text service was changed. Click Apply or Confirm to save it."),
    ("含图片服务已更改，点击应用或确认后保存。", "画像対応サービスを変更しました。「適用」または「確定」をクリックして保存してください。", "The vision service was changed. Click Apply or Confirm to save it."),
    ("{agent} Skill 已更改，点击应用或确认后保存。", "{agent} Skillを変更しました。「適用」または「確定」をクリックして保存してください。", "The {agent} skill was changed. Click Apply or Confirm to save it."),
    ("{agent} Skill 将在应用或确认后卸载。", "{agent} Skillは「適用」または「確定」をクリックした後にアンインストールされます。", "The {agent} skill will be unloaded when you click Apply or Confirm."),
    ("设置未应用；草稿仍保留，可修正后重试或取消。", "設定は適用されていません。下書きは保持されています。修正して再試行するか、キャンセルしてください。", "Settings were not applied. The draft is still available; correct the issue and retry, or cancel."),
    ("设置更改已取消。", "設定の変更をキャンセルしました。", "Settings changes were canceled."),
    ("未应用的设置更改已取消。", "未適用の設定変更をキャンセルしました。", "Unapplied settings changes were canceled."),
    ("选择软件界面显示语言。选择后点击应用或确认才会保存；语言切换会清空两个 Agent 的对话历史和待确认草稿。", "ソフトウェアの表示言語を選択します。選択後、「適用」または「確定」をクリックすると保存されます。言語を切り替えると、両方のAgentの会話履歴と確認待ちの下書きが消去されます。", "Choose the software display language. It is saved when you click Apply or Confirm. Changing the language clears both agents' conversation history and pending drafts."),
    ("显示：", "表示：", "Show: "),
    ("全部商品", "すべての商品", "All items"),
    ("食材", "食材", "Ingredients"),
    ("其他商品", "その他の商品", "Other items"),
    ("待识别", "未分類", "Unclassified"),
    ("肉蛋奶", "肉・卵・乳製品", "Meat, eggs & dairy"),
    ("蔬菜水果", "野菜・果物", "Vegetables & fruit"),
    ("主食粮食", "主食・穀物", "Staples & grains"),
    ("零食点心", "菓子・軽食", "Snacks"),
    ("海鲜水产", "魚介類", "Seafood"),
    ("饮料", "飲料", "Drinks"),
    ("调味干货", "調味料・乾物", "Seasonings & dried goods"),
    ("豆制品", "豆製品", "Beans & tofu"),
    ("熟食冷冻", "調理済み・冷凍食品", "Prepared & frozen"),
    ("采购记录", "購入記録", "Purchases"),
    ("食用记录", "食事記録", "Food log"),
    ("食材与饮食记录", "食材・食事記録", "Food & meal records"),
    ("记录采购商品并按名称自动分类", "購入品を記録し、名称から自動分類", "Record purchases and classify items by name"),
    ("记录购买食材", "食材の購入を記録", "Record food purchase"),
    ("记录吃过的食物", "食べたものを記録", "Record food eaten"),
    ("饮食回顾把已购食品按已吃计入（其他商品不计；待识别项不参与营养分类）", "食事の振り返りで購入食品を食べたものとして扱う（その他商品を除く。未分類品は栄養分類に含めない）", "Count purchased food as eaten in reviews (excludes other items; unclassified items are not used for nutrition categories)"),
    ("刷新", "更新", "Refresh"),
    ("从已记账小票导入商品", "記帳済みレシートから商品を取り込む", "Import items from posted receipts"),
    ("＋ 记录采购食材", "＋ 食材の購入を記録", "+ Record food purchase"),
    ("应用分类", "分類を適用", "Apply category"),
    ("重新自动分类", "自動で再分類", "Reclassify automatically"),
    ("编辑商品/数量", "商品／数量を編集", "Edit item / quantity"),
    ("编辑采购商品", "購入商品を編集", "Edit purchased item"),
    ("食品分类", "食品分類", "Food category"),
    ("分类已应用；名称和数量请点保存后生效。", "分類を適用しました。商品名と数量は保存後に反映されます。", "Category applied. Save to apply the item name and quantity."),
    ("自动分类结果：", "自動分類結果：", "Automatic classification: "),
    ("；点击保存后生效。", "。保存後に反映されます。", "; save to apply."),
    ("移除此商品行", "この商品行を削除", "Remove this item"),
    ("删除选中食用记录", "選択した食事記録を削除", "Delete selected food record"),
    ("每行填写一种食材；数量可写作“名称 | 数量/单位”。", "1行に1つの食材を入力します。数量は「名称 | 数量／単位」の形式で入力できます。", "Enter one item per line. Add a quantity as “name | quantity/unit”."),
    ("每行填写一种食物；数量可写作“名称 | 数量/单位”。", "1行に1つの食品を入力します。数量は「名称 | 数量／単位」の形式で入力できます。", "Enter one food per line. Add a quantity as “name | quantity/unit”."),
    ("餐次（可选）", "食事（任意）", "Meal (optional)"),
    ("备注（可选）", "メモ（任意）", "Note (optional)"),
    ("导入已记账小票商品", "記帳済みレシートの商品を取り込む", "Import posted receipt items"),
    ("选择收据消费。仅导入名称线索明确的食品商品；非食品、占位词和无法确认的商品不加入食材记录，财务流水不变。", "レシート支出を選択します。食品と判断できる手掛かりがある商品だけを取り込みます。非食品、プレースホルダー、判別できない商品は食材記録に追加せず、会計取引は変更しません。", "Select receipt expenses. Import only items with clear food clues; non-food, placeholder, and uncertain items are excluded from food records. Financial entries are unchanged."),
    ("导入所选", "選択項目を取り込む", "Import selected"),
    ("已开启：食品采购计作已吃；其他商品排除，待识别项不参与营养分类。", "有効：購入した食品を食べたものとして扱います。その他商品は除外し、未分類品は栄養分類に含めません。", "Enabled: purchased food counts as eaten. Other items are excluded; unclassified items are not included in nutrition categories."),
    ("饮食回顾只统计食用记录。", "食事の振り返りは食事記録のみを集計します。", "Food reviews use food log records only."),
    ("查看采购商品和自动分类结果", "購入品と自動分類結果を確認", "View purchased items and automatic classifications"),
    ("食材与饮食记录", "食材・食事記録", "Food & meal records"),
    ("支付方式与用途", "支払方法と用途", "Payment methods and purposes"),
    ("管理按场景生效的付款规则", "場面別の支払ルールを管理", "Manage payment rules by scenario"),
    ("每一行都是一条按场景生效的支付规则。填写账户/支付方式、适用币种和用途；币种指交易原币，不是账户币种。选择JPY或CNY后，该规则只用于对应币种的交易；选择“不限”则不限制币种。币种匹配的通用规则优先于不限币种的通用规则，普通消费不会自动换汇。明确说出的付款方式优先；没有唯一匹配项时会先询问。", "各行は場面ごとの支払ルールです。口座／支払方法、対象通貨、用途を入力します。通貨は取引の原通貨を指し、口座通貨ではありません。JPYまたはCNYを選ぶと該当通貨の取引だけに適用され、「指定なし」は通貨を限定しません。通貨が一致する汎用ルールを優先します。通常の支出で自動両替は行いません。ユーザーが明示した支払方法を優先し、一意に決まらない場合は確認します。", "Each row is a scenario-based payment rule. Enter the account/payment method, transaction currency, and purpose. Currency means the original transaction currency, not the account currency. JPY or CNY limits the rule to that currency; Any leaves it unrestricted. A currency-specific general rule takes priority over an unrestricted general rule. Ordinary expenses are not converted automatically. Explicit payment instructions take priority; ambiguous matches prompt for clarification."),
    ("每一行是一条支付场景规则。填写支付方式、适用交易币种和用途。保存后会自动作为个人支付 Skill 随每次记账请求发送，与已加载的记账 Skill 一起提供给 Agent；不会改写你的 Skill 文件。Agent 先理解本次原话，只有语义明确匹配且唯一的规则才会应用；同义表达可以匹配。商家名或宽泛类别通常不能单独触发，但如果规则明确写明某个平台的全部交易都适用，原话提到该平台就能命中。没有规则命中就按原话处理；原话也没有说明支付账户时才追问。", "各行は支払シーンのルールです。支払方法、対象となる取引通貨、用途を入力してください。保存すると、個人用支払Skillとして毎回の記帳リクエストに自動で追加され、読み込み済みの記帳SkillとともにAgentへ送信されます。既存のSkillファイルは変更しません。Agentはまず今回の発言を解釈し、意味が明確に一致する唯一のルールだけを適用します。同義表現は一致とみなします。店名や広いカテゴリだけでは通常適用しませんが、特定プラットフォームの全取引に適用するとルールに明記されている場合は、発言中のプラットフォーム名で一致します。ルールに一致しない場合は発言どおりに処理し、支払口座も不明な場合にのみ確認します。", "Each row is a payment-scenario rule. Enter a payment method, transaction currency, and purpose. When saved, the rules are automatically added as a personal payment Skill to each bookkeeping request alongside your loaded bookkeeping Skill; your Skill file is not modified. The Agent first interprets what you said and applies a rule only when exactly one rule clearly matches its meaning. Synonyms can match. A merchant name or broad category usually cannot trigger a rule by itself, but an explicit rule covering all transactions on a platform matches when your entry names that platform. If no rule matches, it follows your words and asks only when the payment account is also missing."),
    ("支付方式", "支払方法", "Payment method"),
    ("适用币种", "対象通貨", "Currency"),
    ("用途提示", "用途の説明", "Purpose"),
    ("每行是一条场景规则。支付账户从已登记的银行、钱包、预付卡、交通卡或信用卡中选择；积分账户不能作为普通支付账户。点击“扣款顺序”可按实际优先级添加钱包、券、积分和信用卡，积分只在这里作为明确配置的扣款来源。保存后规则会随记账请求提供给 Agent；唯一命中场景时，程序严格按这里的账户顺序和同币种余额/额度分摊，不从用途文字猜顺序，也不跨币种换算。旧规则中无法对应到账户的顺序项会标为“账户未登记”，保存前需添加对应账户或移除该项。", "各行は場面別ルールです。支払口座は登録済みの銀行、ウォレット、プリペイド、交通系IC、クレジットカードから選びます。ポイント口座は通常の支払口座として選べません。「引落順序」でウォレット、券、ポイント、カードを実際の優先順に追加できます。ポイントはここで明示的に設定した場合だけ支払元として使用します。保存したルールは記帳リクエストでAgentに渡されます。場面が一意に一致した場合、プログラムはここで指定した順序と同一通貨の残高・利用可能額で分割し、用途の文章から順序を推測したり通貨を換算したりしません。旧ルールで口座に対応できない順序項目は「口座が未登録」と表示され、保存前に口座を追加するか項目を削除する必要があります。", "Choose a registered bank, wallet, prepaid, transit, or credit account as the payment account; points accounts are excluded. Use Payment order to add wallets, vouchers, points, and cards in their actual priority. Points are used only when explicitly included there. When one scenario rule matches, the app follows this saved order and splits only across same-currency balances or available credit; it does not infer the order from purpose text or convert currencies. Legacy order items that do not match a registered account are marked Account not registered and must be mapped or removed before saving."),
    ("支付账户", "支払口座", "Payment account"),
    ("扣款顺序", "引落順序", "Payment order"),
    ("扣款顺序…", "引落順序…", "Payment order…"),
    ("设置扣款顺序", "引落順序を設定", "Set payment order"),
    ("从上到下依次尝试扣款。可选择积分账户、钱包、预付卡、银行账户或信用卡；一条顺序内必须使用同一币种，积分只能参与JPY顺序。普通支付账户下拉框不显示积分。", "上から順に引き落としを試します。ポイント、ウォレット、プリペイド、銀行口座、クレジットカードを選べます。1つの順序内では通貨を統一し、ポイントはJPYの順序にのみ追加できます。通常の支払口座の選択欄にはポイント口座を表示しません。", "Accounts are tried from top to bottom. You can add points, wallets, prepaid, bank, and credit accounts. Keep each order in one currency; points can only join JPY orders. Points do not appear in the regular payment-account dropdown."),
    ("普通账户", "通常口座", "Regular account"),
    ("账户未登记", "口座が未登録", "Account not registered"),
    ("＋ 添加账户", "＋ 口座を追加", "+ Add account"),
    ("保存顺序", "順序を保存", "Save order"),
    ("一条扣款顺序最多添加10个账户。", "引落順序には最大10口座まで追加できます。", "A payment order can contain up to 10 accounts."),
    ("扣款顺序不完整", "引落順序が不完全です", "Payment order is incomplete"),
    ("{name}：账户未登记", "{name}：口座が未登録", "{name}: account not registered"),
    ("{name}：币种不符（{currency}）", "{name}：通貨が不一致（{currency}）", "{name}: currency mismatch ({currency})"),
    ("{name}：本次已排除", "{name}：今回は対象外", "{name}: excluded for this entry"),
    ("{name}：可用{amount}", "{name}：利用可能{amount}", "{name}: available {amount}"),
    ("尚未记账：本笔需{required}；按顺序{accounts}。合计可用{available}，还差{shortage}。请核对扣款顺序中选中的账户及余额，或说明本次实际付款方式。", "未記帳：必要額{required}。順序：{accounts}。利用可能額の合計は{available}、不足額は{shortage}です。引落順序の口座と残高を確認するか、実際の支払方法を指定してください。", "Not posted: this entry needs {required}. Order: {accounts}. Total available: {available}; shortfall: {shortage}. Check the selected accounts and balances, or specify the actual payment method."),
    ("请为顺序中的每一项选择一个账户。", "順序の各項目で口座を選択してください。", "Choose an account for every step in the order."),
    ("同一账户不能在一条扣款顺序中重复出现。", "同じ口座を引落順序に重複して追加できません。", "An account cannot appear twice in one payment order."),
    ("主支付账户未加入顺序", "支払口座が順序にありません", "Payment account is missing from the order"),
    ("扣款顺序必须包含上方选择的支付账户。", "引落順序には上で選択した支払口座を含めてください。", "The order must include the payment account selected above."),
    ("同一扣款顺序必须全部使用同一币种；积分账户只能加入JPY顺序。", "1つの引落順序では同一通貨を使用してください。ポイント口座はJPYの順序にのみ追加できます。", "All accounts in an order must use the same currency; points accounts can only join JPY orders."),
    ("扣款顺序中包含已不存在的账户，请重新选择。", "引落順序に存在しない口座があります。選び直してください。", "The order includes an account that no longer exists. Choose it again."),
    ("扣款账户币种应与规则适用的交易币种一致；普通消费不会自动换汇。", "引落口座の通貨はルールの対象取引通貨と一致させてください。通常の支出で自動両替は行いません。", "The account currency must match the rule's transaction currency. Ordinary expenses are not converted automatically."),
    ("请选择有效的普通支付账户，并确保扣款顺序包含该账户。", "有効な通常の支払口座を選び、引落順序にも含めてください。", "Choose a valid regular payment account and include it in the payment order."),
    ("扣款顺序中存在无效或重复的账户，请重新设置顺序。", "引落順序に無効または重複した口座があります。設定し直してください。", "The order contains an invalid or duplicate account. Set it again."),
    ("移除扣款账户", "引落口座を外す", "Remove payment account"),
    ("账户重复", "口座が重複しています", "Duplicate account"),
    ("币种不一致", "通貨が一致しません", "Currency mismatch"),
    ("币种不匹配", "通貨が一致しません", "Currency mismatch"),
    ("不限", "指定なし", "Any"),
    ("＋ 添加支付方式", "＋ 支払ルールを追加", "+ Add payment rule"),
    ("支付场景规则已保存；下次发送记账内容时生效。", "支払ルールを保存しました。次回の記帳から適用されます。", "Payment rules saved; they will apply to the next entry."),
    ("支付规则已在其他窗口更新", "支払ルールが別のウィンドウで更新されました", "Payment rules changed in another window"),
    ("支付规则已在其他窗口或同步操作中更新。本次没有覆盖最新设置。请关闭此页后重新打开，再确认并保存。", "支払ルールが別のウィンドウまたは同期処理で更新されたため、最新設定は上書きされませんでした。このページを閉じて開き直し、内容を確認して保存してください。", "Payment rules changed in another window or during sync. The latest settings were not overwritten. Close and reopen this page, then review and save again."),
    ("定期收支", "定期収支", "Recurring transactions"),
    ("管理并自动记入周期性账款", "定期的な収入・支出を管理して自動記帳", "Manage recurring income and expenses"),
    ("设置周期、首次日期、金额、账户和类别。到期时软件会自动在本地账本记入收入或支出；不会连接银行或实际发起付款、收款。软件关闭期间到期的项目会在下次启动时按原日期补记。", "周期、初回日、金額、口座、分類を設定します。期日になるとローカル台帳に収入または支出を記録します。銀行への接続や実際の入出金は行いません。アプリ終了中に期日を迎えた項目は、次回起動時に元の日付で記録します。", "Set the interval, first date, amount, account, and category. When due, the app records income or expenses in the local ledger; it does not connect to a bank or initiate payments. Items that became due while the app was closed are posted with their original dates at next launch."),
    ("新增定期收支", "定期収支を追加", "Add recurring item"),
    ("编辑定期收支", "定期収支を編集", "Edit recurring item"),
    ("下次日期（支持202608、8月）", "次回日（202608、8月などに対応）", "Next date (e.g. 202608 or 2026/8/1)"),
    ("无法编辑", "編集できません", "Cannot edit"),
    ("找不到所选定期收支规则。", "選択した定期収支ルールが見つかりません。", "The selected recurring rule could not be found."),
    ("定期收支规则已更新；只影响后续到期项目，已生成的流水不会改变。", "定期収支ルールを更新しました。今後の期日に適用され、記帳済みの取引は変更されません。", "Recurring rule updated. Changes apply to future due items; existing entries are unchanged."),
    ("所选下次日期已为这条规则生成账目，不能重复安排", "選択した次回日はこのルールですでに記帳済みのため、再設定できません", "This rule already has a posted entry for that date, so it cannot be scheduled again."),
    ("找不到要编辑的定期收支规则", "編集する定期収支ルールが見つかりません", "The recurring rule to edit could not be found."),
    ("项目名称", "項目名", "Item name"),
    ("收支方向", "収支区分", "Income or expense"),
    ("周期", "周期", "Frequency"),
    ("间隔", "間隔", "Interval"),
    ("账户", "口座", "Account"),
    ("类别", "分類", "Category"),
    ("选择并加载文件", "ファイルを選択して読み込む", "Select and load file"),
    ("记账 Skill", "記帳Skill", "Bookkeeping Skill"),
    ("饮食健康 Skill", "食事と健康Skill", "Food & Health Skill"),
    ("选择一个 Markdown Skill 文件。软件会在每次记账前重新读取，并把正文作为补充规则发送给当前 API。只加载所选文件本身，不会自动读取它引用的其他文件或运行其中的命令；程序内置的账务确认和校验规则优先。", "Markdown形式のSkillファイルを選択します。記帳のたびに読み直し、本文を補足ルールとして現在のAPIに送信します。選択したファイルだけを読み込み、参照先のファイルやコマンドは読み込み・実行しません。アプリ内蔵の会計確認と検証ルールを優先します。", "Select a Markdown Skill file. It is re-read before each entry and sent to the current API as supplemental guidance. Only the selected file is loaded; referenced files are not read and commands are not run. Built-in accounting checks take priority."),
    ("Agent 配置与 Skill", "AgentとSkillの設定", "Agent and Skill settings"),
    ("Agent 配置与 Skill", "AgentとSkillの設定", "Agent and Skill settings"),
    ("选择 Agent 后设置它使用的模型服务和 Markdown Skill。两个 Agent 的模型与 Skill 分别保存，Skill 正文只会发送给所选 Agent。", "Agentを選択し、使用するモデルサービスとMarkdown Skillを設定します。2つのAgentの設定は個別に保存され、Skill本文は選択したAgentにのみ送信されます。", "Choose an agent and assign its model service and Markdown Skill. Each agent's settings are saved separately, and Skill text is sent only to the selected agent."),
    ("API 服务", "APIサービス", "API services"),
    ("管理可供两个 Agent 选择的模型连接", "2つのAgentが利用するモデル接続を管理", "Manage model connections available to both agents"),
    ("管理可复用的本机 Ollama 或 OpenAI 兼容服务。每个 Agent 在“Agent 配置与 Skill”页分别选择纯文字服务和含图片服务；修改服务会清除使用它的 Agent 的对话上下文。", "ローカルOllamaまたはOpenAI互換サービスを管理します。各Agentは「AgentとSkillの設定」でテキスト用と画像対応のサービスを選択します。サービスを変更すると、使用中のAgentの会話コンテキストを消去します。", "Manage reusable local Ollama or OpenAI-compatible services. Each agent selects separate text and image services on the Agent and Skill settings page. Changing a service clears the conversation context of agents using it."),
    ("＋ 新建服务", "＋ サービスを追加", "+ Add service"),
    ("配置名称", "設定名", "Profile name"),
    ("Chat Completions 接口完整地址", "Chat Completions APIの完全なURL", "Full Chat Completions endpoint URL"),
    ("模型名称", "モデル名", "Model name"),
    ("API Key（明文显示；本机服务可留空）", "API Key（画面に表示。ローカルサービスは空欄可）", "API key (shown in plain text; may be blank for local services)"),
    ("启用思考模式（仅 DeepSeek 官方接口）", "思考モードを有効にする（DeepSeek公式APIのみ）", "Enable thinking mode (official DeepSeek API only)"),
    ("思考强度", "思考の強さ", "Thinking strength"),
    ("低（low）", "低（low）", "Low"),
    ("高（high）", "高（high）", "High"),
    ("最高（max）", "最大（max）", "Max"),
    ("此选项只会发送到 https://api.deepseek.com。为节省 Token，默认关闭；开启会产生额外推理用量。关闭时强度设置无效，支持的强度取决于所选模型。", "この設定は https://api.deepseek.com にのみ送信されます。トークン節約のため、初期状態ではオフです。オンにすると推論分の使用量が増えます。オフの間は強さの設定は無効で、対応する強さはモデルによって異なります。", "These settings are sent only to https://api.deepseek.com. Thinking is off by default to save tokens; enabling it adds reasoning usage. Strength is inactive while off, and supported levels depend on the model."),
    ("本机 Ollama 可留空 Key；其他服务请填写对应地址、模型和 Key。远程 API 必须使用 HTTPS。Key 在本机加密保存。", "ローカルOllamaではKeyを空欄にできます。他のサービスではURL、モデル名、Keyを入力してください。リモートAPIにはHTTPSが必要です。KeyはこのPCで暗号化して保存されます。", "The key may be blank for local Ollama. For other services, enter the endpoint, model, and key. Remote APIs must use HTTPS. Keys are encrypted on this computer."),
    ("账本与备份", "台帳とバックアップ", "Ledger and backups"),
    ("查看数据位置并创建备份", "データの保存先を確認しバックアップを作成", "View data location and create a backup"),
    ("账本保存在这台电脑上。你可以打开所在文件夹，或创建一份可恢复的 SQLite 备份。", "台帳はこのPCに保存されています。保存フォルダーを開くか、復元可能なSQLiteバックアップを作成できます。", "The ledger is stored on this computer. Open its folder or create a restorable SQLite backup."),
    ("当前账本文件", "現在の台帳ファイル", "Current ledger file"),
    ("打开账本文件夹", "台帳フォルダーを開く", "Open ledger folder"),
    ("小票图片", "レシート画像", "Receipt images"),
    ("保存发送给记账 Agent 的图片到本地", "記帳Agentに送信した画像をローカルに保存", "Save images sent to the bookkeeping agent locally"),
    ("开启后，记账 Agent 发送的图片会压缩后保存在本地文件夹；饮食健康 Agent 图片不会保存。关闭后只影响新发送的图片。", "オンにすると、記帳Agentに送信した画像を圧縮してローカルフォルダーに保存します。食事・健康Agentの画像は保存されません。オフにすると、次回以降に送信する画像だけが対象になります。", "When enabled, images sent to the bookkeeping agent are compressed and saved in a local folder. Food & Health agent images are not saved. Turning this off affects images sent from then on."),
    ("需要 Pillow 压缩；未安装时图片会按原格式保存。", "圧縮にはPillowが必要です。未インストールの場合は元の形式で保存します。", "Pillow is needed for compression. Without it, images are saved in their original format."),
    ("图片文件夹位置", "画像フォルダーの場所", "Image folder location"),
    ("打开图片文件夹", "画像フォルダーを開く", "Open image folder"),
    ("图片保存已开启。", "画像保存を有効にしました。", "Image saving is on."),
    ("图片保存已关闭；已有图片仍保留。", "画像保存を無効にしました。既存の画像は保持されます。", "Image saving is off. Existing images are kept."),
    ("保存设置无法读取；已默认关闭。", "保存設定を読み込めないため、初期設定をオフにしました。", "The save setting could not be read, so saving is off by default."),
    ("图片保存设置无法保存：{error}", "画像保存設定を保存できません：{error}", "Could not save image preferences: {error}"),
    ("无法保存小票图片：{error}", "レシート画像を保存できません：{error}", "Could not save receipt image: {error}"),
    ("无法打开图片文件夹", "画像フォルダーを開けません", "Cannot open image folder"),
    ("图片文件夹", "画像フォルダー", "Image folder"),
    ("无法创建图片文件夹：{error}", "画像フォルダーを作成できません：{error}", "Could not create image folder: {error}"),
    ("无法打开图片文件夹：{error}", "画像フォルダーを開けません：{error}", "Could not open image folder: {error}"),
    ("数据库备份", "データベースのバックアップ", "Database backup"),
    ("创建账本备份", "台帳のバックアップを作成", "Create ledger backup"),
    ("账本保存在这台电脑上。", "台帳はこのPCに保存されています。", "The ledger is stored on this computer."),
    ("账本位置", "台帳の場所", "Ledger location"),
    ("语言", "言語", "Language"),
    ("记账类别", "記帳カテゴリ", "Bookkeeping categories"),
    ("管理记账 Agent 可使用的收入和支出类别", "記帳Agentで使う収入・支出カテゴリを管理", "Manage income and expense categories available to the bookkeeping agent"),
    ("记账设置", "記帳設定", "Bookkeeping settings"),
    ("新增收入或支出类别，并按所选语言维护类别名称。保存后记账 Agent 会在下次请求时读取新类别；已有账目不会改变。", "収入または支出カテゴリを追加し、選択した言語のカテゴリ名を編集します。保存後、記帳Agentは次回のリクエストから新しいカテゴリを読み込みます。既存の取引は変更されません。", "Add income or expense categories and edit their names in the selected language. The bookkeeping agent reads new categories on its next request; existing entries are unchanged."),
    ("新增类别", "カテゴリを追加", "Add a category"),
    ("类别名称", "カテゴリ名", "Category name"),
    ("类别类型", "カテゴリ種別", "Category type"),
    ("添加类别", "カテゴリを追加", "Add category"),
    ("缺少类别名称", "カテゴリ名がありません", "Category name required"),
    ("请填写类别名称。", "カテゴリ名を入力してください。", "Enter a category name."),
    ("缺少类别类型", "カテゴリ種別がありません", "Category type required"),
    ("请选择收入或支出类别。", "収入または支出を選択してください。", "Choose income or expense."),
    ("无法添加类别", "カテゴリを追加できません", "Could not add category"),
    ("类别已添加；记账 Agent 下次请求会读取新类别。", "カテゴリを追加しました。記帳Agentは次回のリクエストから読み込みます。", "Category added; the bookkeeping agent will use it on the next request."),
    ("无法读取类别：", "カテゴリを読み込めません：", "Could not load categories: "),
    ("日语", "日本語", "Japanese"),
    ("英语", "英語", "English"),
    ("显示语言", "表示言語", "Display language"),
    ("编辑所选类别", "選択したカテゴリを編集", "Edit selected category"),
    ("请先选择要编辑的记账类别。", "編集する記帳カテゴリを選択してください。", "Select a bookkeeping category to edit."),
    ("类别名称已保存。", "カテゴリ名を保存しました。", "Category name saved."),
    ("未选择类别", "カテゴリが選択されていません", "No category selected"),
    ("简体中文", "簡体字中国語", "Simplified Chinese"),
    ("日本語", "日本語", "Japanese"),
    ("English", "英語", "English"),
    ("语言与地区", "言語と地域", "Language and region"),
    ("显示设置", "表示設定", "Display settings"),
    ("选择软件界面显示语言", "ソフトウェアの表示言語を選択", "Choose the software display language"),
    ("选择软件界面显示语言。切换前会询问确认；确认后重置记账和饮食健康对话，并立即应用到主窗口和已打开的子窗口。", "ソフトウェアの表示言語を選択します。切り替え前に確認し、確定後は記帳と食事健康の会話をリセットして、メイン画面と開いているウィンドウに反映します。", "Choose the display language. The app asks first; after confirmation, it resets bookkeeping and food-health conversations and applies the change to the main window and open dialogs."),
    ("更改只影响软件界面；账户名、类别和账本记录保留原文。", "変更されるのはソフトウェアの表示だけです。口座名、分類、台帳記録は原文のままです。", "Only the interface changes. Account names, categories, and ledger entries remain as entered."),
    ("语言已切换，将立即生效。", "表示言語を変更しました。すぐに反映されます。", "Language changed and applied."),
    ("确认切换语言", "表示言語の切り替えを確認", "Confirm language change"),
    ("切换语言会清空记账和饮食健康 Agent 的对话历史、待确认草稿，以及尚未发送的文字和图片。是否继续？", "表示言語を切り替えると、記帳と食事健康 Agent の会話履歴、確認待ちの下書き、未送信のテキストと画像が消去されます。続行しますか？", "Changing the language clears both Agents' conversation history, pending drafts, and unsent text and images. Continue?"),
    ("无法切换语言", "表示言語を切り替えられません", "Cannot change language"),
    ("当前任务正在运行；请等任务完成后再切换语言。", "タスクの実行中は切り替えできません。完了後に再試行してください。", "A task is running. Wait for it to finish before changing the language."),
    ("已取消语言切换；对话保持不变。", "表示言語の切り替えをキャンセルしました。会話はそのままです。", "Language change cancelled; conversations were left unchanged."),
    ("语言已切换；所有对话已重置。", "表示言語を切り替え、すべての会話をリセットしました。", "Language changed; all conversations were reset."),
    ("数据管理", "データ管理", "Data management"),
    ("服务与解析", "サービスと解析", "Services and parsing"),
    ("API 服务未配置完整；请填写接口地址和模型名后再试。", "APIサービスが未設定です。URLとモデル名を入力して再試行してください。", "API service is incomplete. Enter the endpoint and model name, then try again."),
    ("当前 API 服务的接口地址或模型名未填写，请先完成设置。", "現在のAPIサービスにURLまたはモデル名がありません。先に設定してください。", "The active API service is missing an endpoint or model name. Complete its settings first."),
    ("当前服务需要 API Key；请先填写并保存。", "現在のサービスにはAPI Keyが必要です。入力して保存してください。", "The active service requires an API key. Enter and save it first."),
    ("尚未配置 API Key；本次没有发送请求。", "API Keyが未設定のため、リクエストは送信されませんでした。", "No API key is configured; the request was not sent."),
    ("API 服务配置已删除。", "APIサービス設定を削除しました。", "API service deleted."),
    ("模型分配已保存。", "モデル割り当てを保存しました。", "Model assignment saved."),
    ("模型已切换；该 Agent 的对话上下文已清空。", "モデルを切り替えました。このAgentの会話履歴を消去しました。", "Model changed; this agent's conversation context was cleared."),
    ("输入完成后自动保存…", "入力が止まると自動保存します…", "Auto-saving when you finish typing…"),
    ("新服务已创建。填写地址、模型和 Key 后会自动保存。", "新しいサービスを作成しました。URL、モデル、Keyを入力すると自動保存されます。", "New service created. The endpoint, model, and key will be saved automatically."),
    ("至少保留一个 API 服务配置。", "APIサービス設定を1件以上残してください。", "At least one API service must remain."),
    ("选择一个 Markdown Skill 文件。", "Markdown形式のSkillファイルを選択してください。", "Select a Markdown Skill file."),
    ("选择记账 Skill 文件", "記帳Skillファイルを選択", "Select bookkeeping Skill file"),
    ("选择并加载文件", "ファイルを選択して読み込む", "Select and load file"),
    ("重新读取", "再読み込み", "Reload"),
    ("记账 Skill 已加载；后续请求会读取最新内容。", "記帳Skillを読み込みました。次回以降は最新の内容を読み込みます。", "Bookkeeping Skill loaded; future requests will use the latest content."),
    ("记账 Skill 已卸载。", "記帳Skillを解除しました。", "Bookkeeping Skill unloaded."),
    ("当前未加载 Skill。", "Skillは読み込まれていません。", "No Skill is loaded."),
    ("当前未加载 Skill。", "Skillは読み込まれていません。", "No Skill is loaded."),
    ("当前 API 服务的接口地址或模型名未填写，请先完成设置。", "現在のAPIサービスにURLまたはモデル名がありません。先に設定してください。", "The active API service is missing an endpoint or model name. Complete its settings first."),
    ("语言和外观", "言語と表示", "Language and display"),
    ("每天", "毎日", "Daily"),
    ("每周", "毎週", "Weekly"),
    ("每月", "毎月", "Monthly"),
    ("每年", "毎年", "Yearly"),
    ("支出", "支出", "Expense"),
    ("收入", "収入", "Income"),
    ("银行", "銀行", "Bank"),
    ("钱包", "ウォレット", "Wallet"),
    ("现金", "現金", "Cash"),
    ("券/预付", "プリペイド／券", "Prepaid / voucher"),
    ("交通卡", "交通系IC", "Transit card"),
    ("积分", "ポイント", "Points"),
    ("推算值", "推算値", "Inferred"),
    ("已确认", "確認済み", "Confirmed"),
    ("用户确认", "ユーザー確認済み", "User confirmed"),
    ("日常一般消费", "日常の一般支出", "General everyday expenses"),
    ("用途提示", "用途の説明", "Purpose"),
    ("已暂停", "一時停止中", "Paused"),
    ("已记录收入", "収入を記録済み", "Income recorded"),
    ("未录入", "未入力", "Not entered"),
    ("未设置", "未設定", "Not set"),
    ("无法估算", "推定できません", "Cannot estimate"),
    ("账单按", "請求は", "Bill recorded in "),
    ("通貨/单位（积分按JPY等值）", "通貨／単位（ポイントはJPY相当）", "Currency / unit (points valued in JPY)"),
    ("家庭财务报表", "家計財務レポート", "Household financial report"),
    ("适用币种", "対象通貨", "Currency"),
    ("用途提示", "用途の説明", "Purpose"),
    ("个人设置", "個人設定", "Preferences"),
    ("Agent 当前使用：", "Agentの現在の設定：", "Current agent: "),
    ("自动保存失败：", "自動保存に失敗しました：", "Auto-save failed: "),
    ("保存失败", "保存に失敗しました", "Save failed"),
    ("删除失败", "削除に失敗しました", "Delete failed"),
    ("无法删除", "削除できません", "Cannot delete"),
    ("无法保存", "保存できません", "Cannot save"),
    ("无法打开", "開けません", "Cannot open"),
    ("无法调整余额", "残高を調整できません", "Cannot adjust balance"),
    ("无法记录还款", "返済を記録できません", "Cannot record repayment"),
    ("无法添加账户", "口座を追加できません", "Cannot add account"),
    ("请选择信用卡", "クレジットカードを選択してください", "Select a credit card"),
    ("请选择资金账户", "資金口座を選択してください", "Select a funds account"),
    ("请填写账户名称。", "口座名を入力してください。", "Enter an account name."),
    ("请填写信用卡名称。", "カード名を入力してください。", "Enter a card name."),
    ("请先选择信用卡与扣款账户", "クレジットカードと引落口座を選択してください", "Select a credit card and payment account first"),
    ("请先选择信用卡与转出账户", "クレジットカードと振替元口座を選択してください", "Select a credit card and source account first"),
    ("请选择信用卡和转出账户。", "クレジットカードと振替元口座を選択してください。", "Select a credit card and source account."),
    ("请选择收入或支出类别", "収入または支出の分類を選択してください", "Select an income or expense category"),
    ("请输入至少一个账户的余额或积分数。", "少なくとも1口座の残高またはポイント数を入力してください。", "Enter a balance or points amount for at least one account."),
    ("没有信用卡账户；请先点击“新增信用卡”。", "クレジットカード口座がありません。「クレジットカードを追加」を選択してください。", "No credit card accounts. Select Add credit card first."),
    ("还没有登记信用卡；点击“新增信用卡”开始。", "カードが登録されていません。「クレジットカードを追加」から登録してください。", "No credit cards are registered. Select Add credit card to begin."),
    ("没有填写余额", "残高が入力されていません", "No balance entered"),
    ("请先退出调整", "先に調整を終了してください", "Finish the adjustment first"),
    ("账户尚未创建", "口座はまだ作成されていません", "Account has not been created"),
    ("这行是等待首次盘点的实体现金项目，目前没有可删除的账户。", "この行は初回棚卸し待ちの現金です。削除できる口座はまだありません。", "This is a cash item awaiting its first count; there is no account to delete."),
    ("保存或取消余额调整后再删除账户。", "残高調整を保存またはキャンセルしてから口座を削除してください。", "Save or cancel the balance adjustment before deleting an account."),
    ("该卡尚未保存每月应还计划。", "このカードには毎月の返済予定がありません。", "No monthly repayment plan is saved for this card."),
    ("还款需要明确选择转出账户和信用卡。提交后只记账户间转账，不增加消费；额度快照仍以你重新录入的卡片应用数值为准。", "返済時は振替元口座とクレジットカードを選択してください。保存すると口座間振替だけを記録し、支出は増やしません。利用枠はカードアプリから再入力したスナップショットを基準にします。", "Select the source account and credit card. Saving records a transfer only; it does not add an expense. Credit limits remain based on the snapshot you enter from the card app."),
    ("支持的图片", "対応画像", "Supported images"),
    ("请把 JPG、PNG 或 WebP 图片拖入输入框。", "JPG、PNG、WebP画像を入力欄にドロップしてください。", "Drop JPG, PNG, or WebP images into the input box."),
    ("拖放依赖未安装；请点击添加图片", "ドラッグ＆ドロップ機能がありません。「画像を追加」を選択してください", "Drag-and-drop is unavailable; select Add image."),
    ("拖放初始化失败；请点击添加图片", "ドラッグ＆ドロップを初期化できませんでした。「画像を追加」を選択してください", "Could not initialize drag-and-drop; select Add image."),
    ("图片总大小超过24 MB，请减少图片数量或压缩图片。", "画像の合計サイズが24 MBを超えています。枚数を減らすか圧縮してください。", "Images exceed the 24 MB total limit. Remove or compress some images."),
    ("账本备份已保存到：\n", "台帳のバックアップを保存しました：\n", "Ledger backup saved to:\n"),
    ("账本文件夹不存在：\n", "台帳フォルダーが見つかりません：\n", "Ledger folder does not exist:\n"),
    ("API 配置错误", "API設定エラー", "API configuration error"),
    ("无法读取报表", "レポートを読み込めません", "Cannot read report"),
    ("无法打开账本文件夹：\n", "台帳フォルダーを開けません：\n", "Cannot open ledger folder:\n"),
    ("没有可导入的小票", "取り込めるレシートがありません", "No receipts to import"),
    ("没有找到含有可确认食品、且尚未导入的已记账小票。纯非食品小票和无法确认的商品不会进入食材记录。", "食品と確認できる商品があり、未取り込みの記帳済みレシートはありません。非食品のみのレシートや判別できない商品は食材記録に追加されません。", "No unimported posted receipts with confirmed food items were found. Receipts containing only non-food or uncertain items are excluded from food records."),
    ("已导入 {count} 条可识别食品商品行；非食品和无法确认的项目不加入食材记录。", "食品と判定できる商品を{count}件取り込みました。非食品や判別できない項目は食材記録に追加していません。", "Imported {count} confirmed food item(s). Non-food and uncertain items were excluded from food records."),
    ("已将 {count} 条可确认食品商品行加入“食材与饮食记录”", "確認できた食品の商品行を{count}件「食材・食事記録」に追加しました", "Added {count} confirmed food item(s) to Food & Meal Records"),
    ("小票商品未识别到明确食品，未新增食材记录", "食品と確認できる商品が見つからなかったため、食材記録は追加していません", "No confirmed food items were found, so no food records were added"),
    ("请选择小票", "レシートを選択してください", "Select a receipt"),
    ("请先选择至少一张小票。", "レシートを1枚以上選択してください。", "Select at least one receipt."),
    ("请选择商品", "商品を選択してください", "Select an item"),
    ("请先选择一条采购商品记录。", "購入記録を1件選択してください。", "Select a purchase record first."),
    ("请先选择一条食用记录。", "食事記録を1件選択してください。", "Select a food log entry first."),
    ("请选择记录", "記録を選択してください", "Select a record"),
    ("保存失败", "保存に失敗しました", "Save failed"),
    ("更新失败", "更新に失敗しました", "Update failed"),
    ("读取失败", "読み込みに失敗しました", "Read failed"),
    ("导入失败", "取り込みに失敗しました", "Import failed"),
    ("自动分类失败", "自動分類に失敗しました", "Automatic classification failed"),
    ("无法加载 Skill", "Skillを読み込めません", "Cannot load Skill"),
    ("卸载失败", "解除に失敗しました", "Unload failed"),
    ("删除 API 服务", "APIサービスを削除", "Delete API service"),
    ("删除定期收支规则", "定期収支ルールを削除", "Delete recurring rule"),
    ("删除现金管理账户", "現金管理口座を削除", "Delete cash account"),
    ("删除账户", "口座を削除", "Delete account"),
    ("删除支付规则行", "支払ルールを削除", "Delete payment rule"),
    ("移除采购商品记录", "購入商品記録を削除", "Remove purchase record"),
    ("删除食用记录", "食事記録を削除", "Delete food log"),
    ("数据管理", "データ管理", "Data management"),
    ("默认", "既定", "Default"),
    ("JPY合并口径", "JPY合算", "Combined JPY"),
    ("小票识别", "レシート認識", "Receipt recognition"),
    ("文字解析", "テキスト解析", "Text parsing"),
    ("手工记录", "手入力", "Manual entry"),
    ("历史小票导入", "過去のレシートから取り込み", "Imported from past receipt"),
    ("输入实际余额", "実際の残高を入力", "Enter actual balance"),
    ("餐饮", "外食", "Dining"),
    ("日用品", "日用品", "Household goods"),
    ("其他损耗", "その他の損失", "Other loss"),
    ("煤气费", "ガス代", "Gas bill"),
    ("食材", "食材", "Ingredients"),
    ("日常一般消费", "日常の一般支出", "General everyday expenses"),
    ("午餐", "昼食", "Lunch"),
    ("晚餐", "夕食", "Dinner"),
    ("早餐", "朝食", "Breakfast"),
    ("加餐", "間食", "Snack"),
    ("其他", "その他", "Other"),
    ("全部商品", "すべての商品", "All items"),
    ("删除规则", "ルールを削除", "Delete rule"),
    ("取消编辑", "編集をキャンセル", "Cancel editing"),
    ("PNG 图片", "PNG画像", "PNG images"),
    ("JPEG 图片", "JPEG画像", "JPEG images"),
    ("WebP 图片", "WebP画像", "WebP images"),
    ("使用的模型服务", "使用するモデルサービス", "Model service"),
    ("Markdown 文件", "Markdownファイル", "Markdown files"),
    ("日期（支持202608、8月）", "日付（202608、8月などに対応）", "Date (e.g. 202608 or 2026/8/1)"),
    ("Skill 文件 (SKILL.md)", "Skillファイル (SKILL.md)", "Skill files (SKILL.md)"),
    ("尚未配置可用的模型服务。请先在“API 服务”页添加服务。", "利用可能なモデルサービスがありません。「APIサービス」ページでサービスを追加してください。", "No model services are available. Add one on the API services page."),
    ("某项定期收支积欠超过100期；本轮已处理100期，将继续分批补记。", "一部の定期収支が100回を超えて未処理です。今回は100回を処理し、残りは次回以降に分けて記帳します。", "A recurring item is over 100 periods behind. This run processed 100; remaining entries will be posted in later batches."),
    ("记录购买的食材和食品，按本地规则自动归类为肉蛋奶、蔬菜水果、主食粮食、零食点心等；名称不明确时保留为待识别，你可以手动修改。数量按原文保存，不会自动估算库存。饮食回顾可按你的偏好把已购食品视为已吃，不需要单独登记食用记录。", "購入した食材や食品を記録し、ローカルルールで肉・卵・乳製品、野菜・果物、主食、菓子などに分類します。名称が不明確な項目は未分類のままにし、手動で変更できます。数量は入力どおりに保存し、在庫を自動推定しません。設定により、購入した食品を食べたものとして食事の振り返りに含められます。", "Record purchased food and classify it locally as meat/eggs/dairy, produce, staples, snacks, and more. Unclear names remain unclassified and can be changed manually. Quantities are saved as entered; inventory is not estimated. You can choose whether purchased food counts as eaten in food reviews."),
    ("未设置", "未設定", "Not set"),
    ("支付场景规则：未设置", "支払ルール：未設定", "Payment rules: not configured"),
    ("支付场景规则：设置文件无法读取，请打开“支付方式与用途”重新保存。", "支払ルール設定ファイルを読み込めません。「支払方法と用途」を開いて再保存してください。", "Could not read payment rules. Open Payment methods and purposes and save them again."),
    ("正在读取账本…", "台帳を読み込んでいます…", "Loading ledger…"),
    ("请选择一项", "項目を選択してください", "Select an item"),
    ("周期性账款", "定期的な請求", "Recurring bills"),
    ("请输入", "入力してください", "Please enter"),
    ("记账 Agent", "家計簿Agent", "Bookkeeping agent"),
    ("饮食健康 Agent", "食事と健康Agent", "Food & Health agent"),
    ("Ollama 本机", "Ollama（ローカル）", "Ollama (local)"),
    ("环境变量 API", "環境変数のAPI", "Environment API"),
    ("未命名服务", "名前のないサービス", "Unnamed service"),
    ("未填写模型", "モデル未入力", "No model entered"),
    ("旧 NVIDIA 配置（请更新密钥）", "旧NVIDIA設定（Keyを更新してください）", "Legacy NVIDIA profile (update key)"),
    ("Key 已在本机加密保存", "KeyはこのPCで暗号化して保存済み", "Key encrypted and saved locally"),
    ("未填写 Key", "Key未入力", "No key entered"),
    ("项目", "項目", "Item"),
    ("方向", "種別", "Type"),
    ("账单金额→扣款币种", "請求額 → 引落通貨", "Bill amount → payment currency"),
    ("账户（币种）", "口座（通貨）", "Account (currency)"),
    ("类别", "分類", "Category"),
    ("周期", "周期", "Frequency"),
    ("下次日期", "次回日付", "Next date"),
    ("状态", "状態", "Status"),
    ("币种", "通貨", "Currency"),
    ("信用卡", "クレジットカード", "Credit card"),
    ("历史记录", "履歴", "History"),
    ("快照日期", "スナップショット日", "Snapshot date"),
    ("转出账户", "振替元口座", "Source account"),
    ("还款金额", "返済額", "Repayment amount"),
    ("说明", "説明", "Details"),
    ("商品/食材", "商品／食材", "Item / ingredient"),
    ("分类", "分類", "Classification"),
    ("来源", "出典", "Source"),
    ("账本流水", "台帳取引", "Ledger entry"),
    ("餐次", "食事", "Meal"),
    ("吃了什么", "食べたもの", "Food"),
    ("历史不完整", "履歴不完全", "Incomplete history"),
    ("完整记录", "完全な記録", "Complete records"),
    ("期初为推算", "開始残高は推算値", "Inferred opening balance"),
    ("参考汇率", "参考為替レート", "Reference exchange rate"),
    ("期初账面卡债", "開始時の台帳上カード債務", "Opening card debt on ledger"),
    ("债务记录状态", "債務記録の状態", "Debt record status"),
    ("账单", "請求", "Bill"),
    ("余额/点数（平时只读）", "残高／ポイント（通常は読み取り専用）", "Balance / points (read-only)"),
    ("操作", "操作", "Actions"),
    ("已确认账面负债", "確認済み台帳負債", "Confirmed ledger liabilities"),
    ("账户余额/点数（平时只读）", "口座残高／ポイント（通常は読み取り専用）", "Account balance / points (read-only)"),
    ("资产负债", "資産・負債", "Assets & liabilities"),
    ("资产", "資産", "Assets"),
    ("负债", "負債", "Liabilities"),
    ("积分（不计入资产）", "ポイント（資産に含まない）", "Points (excluded from assets)"),
    ("当前显示", "表示中", "Showing"),
    ("还款 #", "返済 #", "Repayment #"),
    ("另有", "ほかに", "Plus"),
    ("下次还款日", "次回返済日", "Next due date"),
    ("暂停", "一時停止", "Paused"),
    ("恢复", "再開", "Resumed"),
    ("本期首次盘点：期初余额", "初回棚卸し：開始残高", "Initial count: opening balance"),
    ("与账面一致，没有新增分录。", "台帳残高と一致しています。仕訳は追加されていません。", "Matches the ledger; no entry was added."),
    ("默认首次盘点行已一并移除；需要时可用同名钱包账户重新添加。", "初回棚卸し用の行も削除しました。必要であれば同じ名前のウォレット口座を追加できます。", "The default initial-count row was also removed. You can add a wallet account with the same name if needed."),
    ("每月应还计划已恢复", "毎月返済予定を再開しました", "Monthly repayment plan resumed"),
    ("每月应还计划已暂停", "毎月返済予定を一時停止しました", "Monthly repayment plan paused"),
    ("已按本期单独填写的金额在本地账本记入", "今期に入力した金額をローカル台帳に記帳しました", "Posted the amount entered for this period to the local ledger"),
    ("可用额度已按记录更新，未另记消费。若还没有额度快照，仍需先录入快照。", "利用可能額を記録に基づいて更新しました。支出は追加していません。利用枠スナップショットがない場合は、先に入力してください。", "Available credit was updated from the repayment record; no expense was added. Enter a credit limit snapshot if none exists."),
    ("当前记账请求完成后再查看食材与饮食记录。", "現在の記帳リクエストが完了してから食材・食事記録を確認してください。", "Wait for the current bookkeeping request to finish before opening food records."),
    ("当前记账请求完成后再管理定期收支。", "現在の記帳リクエストが完了してから定期収支を管理してください。", "Wait for the current bookkeeping request to finish before managing recurring transactions."),
    ("当前记账请求完成后再查看报表。", "現在の記帳リクエストが完了してからレポートを確認してください。", "Wait for the current bookkeeping request to finish before opening reports."),
    ("当前记账请求完成后再调整现金。", "現在の記帳リクエストが完了してから現金を調整してください。", "Wait for the current bookkeeping request to finish before adjusting cash."),
    ("当前记账请求完成后再管理信用卡。", "現在の記帳リクエストが完了してからクレジットカードを管理してください。", "Wait for the current bookkeeping request to finish before managing credit cards."),
    ("当前请求完成后再切换 API 服务。", "現在のリクエストが完了してからAPIサービスを切り替えてください。", "Wait for the current request to finish before switching API services."),
    ("备份失败", "バックアップに失敗しました", "Backup failed"),
    ("备份完成", "バックアップが完了しました", "Backup complete"),
    ("尚无还款计划", "返済予定がありません", "No repayment plan"),
    ("无法保存每月应还计划", "毎月の返済予定を保存できません", "Cannot save monthly repayment plan"),
    ("无法保存额度", "利用枠を保存できません", "Cannot save credit limit"),
    ("无法删除账户", "口座を削除できません", "Cannot delete account"),
    ("无法新增信用卡", "クレジットカードを追加できません", "Cannot add credit card"),
    ("无法更新计划", "予定を更新できません", "Cannot update plan"),
    ("无法读取拖入文件", "ドロップしたファイルを読み込めません", "Cannot read dropped file"),
    ("有用途提示的项目还没有填写支付方式。", "用途が設定された行に支払方法が入力されていません。", "A payment method is missing for a rule with a purpose."),
    ("缺少信用卡名称", "クレジットカード名が未入力です", "Credit card name is required"),
    ("缺少期初余额", "開始残高が未入力です", "Opening balance is required"),
    ("缺少账户名称", "口座名が未入力です", "Account name is required"),
    ("请先选择要记录额度的信用卡。", "利用枠を記録するクレジットカードを選択してください。", "Select the credit card whose limit you want to record."),
    ("请填写支付方式", "支払方法を入力してください", "Enter a payment method"),
    ("请选择信用卡与扣款账户。", "クレジットカードと引落口座を選択してください。", "Select a credit card and payment account."),
    ("账户不完整", "口座情報が不足しています", "Account details are incomplete"),
    ("部分图片未添加", "一部の画像を追加できませんでした", "Some images were not added"),
    ("无法打开食材记录", "食材記録を開けません", "Cannot open food records"),
    ("移除失败", "削除に失敗しました", "Could not remove item"),
    ("可按当前顺序或币种排序。点击“调整差额”后编辑余额；新增账户时请填写真实期初余额和日期。", "現在の順序または通貨で並べ替えできます。「差額を調整」を選ぶと残高を編集できます。口座を追加する際は、実際の開始残高と日付を入力してください。", "Sort by the current order or by currency. Select Adjust balance to edit amounts. Enter the actual opening balance and date when adding an account."),
    ("真实历史卡债未核实；期初值仅为本账本记录起点", "過去の実際のカード債務は未確認です。開始値はこの台帳での記録開始点にすぎません", "Historical card debt has not been verified; this opening value is only the starting point for this ledger"),
    ("规则已删除，历史账本流水已保留。", "ルールを削除しました。過去の台帳取引は保持されています。", "Rule deleted; historical ledger entries were kept."),
    ("请先选择一项定期收支。", "定期収支を選択してください。", "Select a recurring transaction first."),
    ("可登记新卡、保存额度快照或记录还款。", "カードの登録、利用枠スナップショットの保存、返済の記録ができます。", "Register cards, save credit limit snapshots, or record repayments."),
    ("账单币种与付款账户币种独立选择。下拉框含现金管理账户和信用卡、不含积分账户；币种不同时，到期按账单日期参考汇率换算账户扣款。实际扣款可能与参考汇率有差异，请以付款账户账单核对。", "請求通貨と支払口座の通貨は別々に選択します。口座一覧には現金管理口座とクレジットカードを表示し、ポイント口座は含めません。通貨が異なる場合、期日に請求日基準の参考レートで引落額を換算します。実際の引落額は異なる場合があるため、支払口座の明細を確認してください。", "Select the bill currency and payment account currency separately. The list includes cash accounts and credit cards, but not points accounts. If currencies differ, the due amount is converted using the bill-date reference rate. Verify the actual amount on the payment account statement."),
    ("账本中还没有可选的现金管理账户或信用卡；请先添加银行、钱包、券/预付、交通卡或信用卡账户。", "選択できる現金管理口座またはクレジットカードがありません。銀行、ウォレット、プリペイド、交通系IC、またはクレジットカード口座を追加してください。", "No cash management account or credit card is available. Add a bank, wallet, prepaid, transit, or credit card account first."),
    ("只移除此商品记录，不会删除对应的财务流水。", "この商品記録だけを削除し、対応する会計取引は削除しません。", "Only this item record will be removed; the related financial transaction will remain."),
    ("这条饮食记录将从本地账本数据库中永久删除。", "この食事記録はローカル台帳データベースから完全に削除されます。", "This food log entry will be permanently deleted from the local ledger database."),
    ("删除后将不再自动记账；已经生成的账本流水会保留。", "削除後は自動記帳されなくなります。作成済みの台帳取引は保持されます。", "This rule will no longer post automatically. Existing ledger entries will remain."),
    ("已有账本流水、定期收支或还款计划的账户不能删除。删除前会自动备份账本；若支付规则中写有此账户名称，删除后请到“支付方式与用途”同步修改。", "台帳取引、定期収支、返済予定で使用中の口座は削除できません。削除前に台帳をバックアップします。支払ルールにこの口座名が含まれている場合は、「支払方法と用途」でも変更してください。", "Accounts used by ledger entries, recurring transactions, or repayment plans cannot be deleted. The ledger is backed up first. If a payment rule names this account, update that rule under Payment Methods and Purposes."),
    ("使用此服务的 Agent 会改用其他服务，并清除对应的模型对话上下文。", "このサービスを使うAgentは別のサービスに切り替わり、該当する会話コンテキストが消去されます。", "Agents using this service will switch to another service, and their conversation context will be cleared."),
    ("该规则行会从当前编辑列表移除；点击保存后才会从支付设置中删除。", "このルール行は編集中の一覧から削除されます。支払設定から削除されるのは保存後です。", "This rule will be removed from the current edit list. It is deleted from payment settings only after you save."),
    ("请填写当前已确认的余额/点数；未知时可填0并标记为记录不完整。", "現在確認できている残高／ポイントを入力してください。不明な場合は0を入力し、記録不完全として登録できます。", "Enter the confirmed balance or points. If unknown, enter 0 and mark the records incomplete."),
    ("新增定期收入或支出；暂停后不会自动记账。", "定期収入または支出を追加します。一時停止中は自動記帳されません。", "Add recurring income or expenses. Paused items are not posted automatically."),
    ("可登记新卡、保存额度快照或记录还款。", "カードの登録、利用枠スナップショットの保存、返済の記録ができます。", "Register cards, save credit limit snapshots, or record repayments."),
    ("请先完成或取消当前余额盘点，再提交图片。", "画像を送信する前に、現在の残高確認を完了またはキャンセルしてください。", "Finish or cancel the current balance count before sending an image."),
    ("上一笔余额盘点还没有完成，请先回答上一个问题，或说‘取消这笔’。", "前の残高確認が未完了です。質問に答えるか「取消」と入力してください。", "The previous balance count is incomplete. Answer the question or say cancel."),
    ("有多个账户符合这个名称：{accounts}。请说完整账户名称。", "該当する口座が複数あります：{accounts}。正式な口座名を指定してください。", "Multiple accounts match: {accounts}. Specify the full account name."),
    ("请告诉我盘点的是哪个账户。", "残高を確認する口座を指定してください。", "Which account are you counting?"),
    ("已识别账户 {account}。请告诉我盘点后实际剩余多少；不是填写差额。", "口座 {account} を確認しました。差額ではなく、確認後の実際の残高を入力してください。", "Account {account} identified. Enter the actual remaining balance, rather than the difference."),
    ("请告诉我实际盘点日期，不能使用未来日期。", "実際の確認日を入力してください。未来の日付は使用できません。", "Enter the actual count date; it cannot be in the future."),
    ("余额盘点未记账：{error}", "残高確認は記帳されませんでした：{error}", "Balance count was not posted: {error}"),
    ("请重新填写盘点后的实际余额。", "確認後の実際の残高をもう一度入力してください。", "Enter the actual counted balance again."),
    ("可用额度", "利用可能額", "available credit"),
    ("已完成 {account} 的{subject}盘点：账面 {before}，实际 {counted}；已记录{category} {difference}。{date}", "{account} の{subject}を確認しました。帳簿 {before}、実際 {counted}。{category} {difference} を記帳しました。{date}", "Counted {subject} for {account}: book {before}, actual {counted}; recorded {category} of {difference}. {date}"),
    ("已核对 {account} 的{subject}：账面与实际均为 {counted}，没有差额，无需新增流水。{date}", "{account} の{subject}を確認しました。帳簿と実際はともに {counted} で、差額はありません。{date}", "Checked {subject} for {account}: book and actual are both {counted}; no entry was needed. {date}"),
    ("盘点金额的币种与所选账户不一致，请核对。", "確認金額の通貨が選択した口座と一致しません。", "The counted amount's currency does not match the account."),
    ("盘点日期早于账户的期初日期，请核对。", "確認日が口座の開始日より前です。", "The count date is before the account opening date."),
    ("这张信用卡没有可用额度快照，请先在信用卡管理中设置总额度和可用额度。", "このカードの利用可能額スナップショットがありません。先にカード管理で利用枠と利用可能額を設定してください。", "This card has no available-credit snapshot. Set its credit limit and available credit in Credit Card Management first."),
    ("盘点后的可用额度不能超过该卡总额度，请核对。", "確認後の利用可能額はカードの利用枠を超えられません。", "The counted available credit cannot exceed the card's credit limit."),
    ("这张信用卡在盘点日期之后已有流水或额度快照，请先核对后续记录，再调整该日期的余额。", "確認日より後のカード取引または利用枠スナップショットがあります。後続の記録を確認してから調整してください。", "This card has transactions or credit snapshots after the count date. Review those later records before adjusting this date."),
    ("账本正在执行其他写入，请稍后再盘点。", "台帳に別の書き込みを実行中です。後ほど残高を確認してください。", "The ledger is processing another write. Try the count again shortly."),
    ("账单记录", "取引履歴", "Transaction history"),
    ("按日期查看近期收入、支出和转账", "日付を指定して最近の収入・支出・振替を表示", "View recent income, expenses, and transfers by date"),
    ("当前记账请求完成后再查看账单记录。", "現在の記帳リクエストが完了してから取引履歴を確認してください。", "Wait for the current bookkeeping request to finish before viewing transactions."),
    ("查看本地账本中的收入、支出和转账。按账本日期筛选；各币种金额分别显示。", "ローカル台帳の収入・支出・振替を表示します。台帳の日付で絞り込み、通貨ごとに金額を表示します。", "View income, expenses, and transfers in the local ledger. Filter by ledger date; amounts stay separate by currency."),
    ("指定日期", "日付を指定", "One day"),
    ("最近几天", "最近の日数", "Recent days"),
    ("日期 / 截止日期（支持202608、8月）", "日付／終了日（202608、8月などに対応）", "Date / through (e.g. 202608 or 2026/8/1)"),
    ("选择日期", "日付を選択", "Select a date"),
    ("选择…", "選択…", "Select…"),
    ("周一", "月", "Mo"),
    ("周二", "火", "Tu"),
    ("周三", "水", "We"),
    ("周四", "木", "Th"),
    ("周五", "金", "Fr"),
    ("周六", "土", "Sa"),
    ("周日", "日", "Su"),
    ("天数", "日数", "Days"),
    ("查看", "表示", "Show"),
    ("今天", "今日", "Today"),
    ("编号", "番号", "ID"),
    ("类型", "種類", "Type"),
    ("说明", "説明", "Description"),
    ("账户 / 转账方向", "口座／振替方向", "Account / transfer"),
    ("筛选条件有误", "検索条件エラー", "Invalid filter"),
    ("日期无效或格式不支持。支持 YYYY-MM-DD、YYYY/M/D、YYYYMMDD、YYYYMM 和 M月；仅写月份时按当前日本年份的1日处理。", "日付が無効か形式が未対応です。YYYY-MM-DD、YYYY/M/D、YYYYMMDD、YYYYMM、M月に対応しています。月だけの場合は現在の日本の年のその月の1日として扱います。", "The date is invalid or unsupported. Use YYYY-MM-DD, YYYY/M/D, YYYYMMDD, YYYYMM, or M月. A month without a year uses the first day of that month in the current Japan-local year."),
    ("天数请输入 1 到 3650 之间的整数", "日数は1～3650の整数で入力してください", "Enter a whole number of days from 1 to 3650"),
    ("无法读取账单", "取引履歴を読み込めません", "Could not load transactions"),
    ("账户扣款", "口座引落額", "account debit"),
    ("转账", "振替", "Transfer"),
    ("备查", "参考記録", "Memo"),
    ("已入账", "記帳済み", "Posted"),
    ("找到 {count} 条记录：{start} 至 {end}", "{start}～{end}の取引：{count}件", "{count} transactions: {start} through {end}"),
    ("待核对", "要確認", "Review"),
    ("删除选中分录", "選択した仕訳を削除", "Delete selected entry"),
    ("删除账务分录", "仕訳を削除", "Delete ledger entry"),
    ("未选择流水", "取引が選択されていません", "No entry selected"),
    ("请先选择一条账务记录。", "削除する取引を選択してください。", "Select a ledger entry first."),
    ("所选流水编号无效，请刷新账单记录后重试。", "選択した取引番号が無効です。履歴を更新して再試行してください。", "The selected entry ID is invalid. Refresh the history and try again."),
    ("所选流水已不在当前列表中，请刷新后重试。", "選択した取引は現在の一覧にありません。更新して再試行してください。", "The selected entry is no longer in this list. Refresh and try again."),
    ("编辑选中分录", "選択した仕訳を編集", "Edit selected entry"),
    ("编辑账务分录", "仕訳を編集", "Edit ledger entry"),
    ("无法编辑", "編集できません", "Could not edit entry"),
    ("无法保存修改", "変更を保存できません", "Could not save changes"),
    ("分录已更新", "仕訳を更新しました", "Entry updated"),
    ("确认修改", "変更を確定", "Confirm changes"),
    ("流水 #{id} 已更新。修改前备份：{backup}", "取引 #{id} を更新しました。変更前のバックアップ：{backup}", "Updated entry #{id}. Pre-edit backup: {backup}"),
    ("转入账户", "振替先口座", "Destination account"),
    ("转入金额", "振替先金額", "Destination amount"),
    ("保存后会重新计算相关余额和报表；修改前会自动备份账本。", "保存後に関連する残高とレポートを再計算し、変更前に台帳を自動バックアップします。", "Related balances and reports are recalculated after saving. The ledger is backed up first."),
    ("请选择有效的账务类型。", "有効な取引種類を選択してください。", "Choose a valid transaction type."),
    ("请选择有效的账户，或选择备查。", "有効な口座を選択するか、参考記録を選択してください。", "Choose a valid account or select Memo."),
    ("请选择有效类别。", "有効なカテゴリを選択してください。", "Choose a valid category."),
    ("所选类别与交易类型不匹配。", "選択したカテゴリが取引種類と一致しません。", "The selected category does not match the transaction type."),
    ("所选流水已不存在，请刷新账单记录后重试。", "選択した取引は既にありません。履歴を更新して再試行してください。", "The selected entry no longer exists. Refresh the history and try again."),
    ("这条流水关联着信用卡自动还款计划，请在还款管理中调整，避免计划金额与账目不一致。", "この取引はクレジットカードの自動返済予定に関連しています。予定金額との不一致を防ぐため、返済管理で調整してください。", "This entry is linked to an automatic credit card repayment. Edit it in repayment management to keep the scheduled amount consistent."),
    ("这笔支出关联着采购商品记录，请先在食材与饮食记录中处理关联商品，再修改账务类型。", "この支出には購入商品記録が関連付けられています。取引種類を変更する前に、食材・食事記録で関連商品を処理してください。", "This expense has linked purchased items. Handle those items in Food and Meal Records before changing the transaction type."),
    ("账本正在执行其他写入，暂时无法编辑流水", "台帳で別の書き込みを実行中のため、取引を編集できません", "The ledger is processing another write and cannot edit this entry yet."),
    ("流水已在其他窗口中改变，请刷新账单记录后重试。", "取引が別のウィンドウで変更されました。履歴を更新して再試行してください。", "This entry changed in another window. Refresh the history and try again."),
    ("流水状态已改变，请刷新后重试。", "取引の状態が変更されました。更新して再試行してください。", "The entry changed. Refresh and try again."),
    ("账务记录必须使用货币币种", "取引には通貨を指定してください", "Ledger entries must use a monetary currency."),
    ("已停用类别不能用于这笔账务记录。", "無効化されたカテゴリはこの取引に使用できません。", "An inactive category cannot be used for this entry."),
    ("转出账户和转入账户不能相同", "振替元と振替先に同じ口座は指定できません", "The source and destination accounts must be different."),
    ("转账日期不能早于任一账户期初日期", "振替日はどちらかの口座開始日より前にできません", "The transfer date cannot be earlier than either account's opening date."),
    ("转出金额币种必须与转出账户一致", "振替元の金額通貨は口座通貨と一致させてください", "The outgoing amount currency must match the source account."),
    ("转账必须同时指定转出和转入账户", "振替元と振替先の両方を指定してください", "Choose both source and destination accounts."),
    ("跨币种转账必须填写转入金额", "異なる通貨間の振替では振替先金額を入力してください", "Enter the destination amount for a cross-currency transfer."),
    ("转账不能作为备查交易", "振替を参考記録にはできません", "Transfers cannot be memo-only entries."),
    (
        "该流水将从本地账本永久删除，相关账户余额和收支报表会按剩余流水重新计算。关联的采购商品会一并删除；若它是自动还款流水，关联的本期自动还款会取消，避免重复记账。已有余额快照和独立食用记录不变。删除前会自动备份账本。",
        "この取引はローカル台帳から完全に削除され、関連口座の残高と収支レポートは残りの取引から再計算されます。関連する購入商品も削除されます。自動返済の取引の場合、二重記帳を防ぐため当期の自動返済との関連を取り消します。既存の残高スナップショットと独立した食事記録は変更されません。削除前に台帳をバックアップします。",
        "This entry will be permanently removed from the local ledger, and affected account balances and reports will be recalculated from the remaining entries. Linked purchased-item rows will also be removed. If this is an automatic repayment, its current-period schedule link will be canceled to prevent duplicate posting. Existing balance snapshots and independent food logs will remain unchanged. A backup is created first.",
    ),
    ("分录已删除", "仕訳を削除しました", "Entry deleted"),
    ("已删除流水 #{id}。删除前备份：{backup}", "取引 #{id} を削除しました。削除前のバックアップ：{backup}", "Deleted entry #{id}. Pre-deletion backup: {backup}"),
    ("固定资产与折旧", "固定資産と減価償却", "Fixed assets and depreciation"),
    ("登记大额资产，查看月度折旧和报废价值", "高額資産を登録し、月次減価償却と廃棄時価値を確認", "Register major assets and view monthly depreciation and disposal value"),
    ("资产管理", "資産管理", "Asset Management"),
    ("管理投资资产与固定资产，查看资产价格、月度折旧和账面价值", "投資資産と固定資産を管理し、資産価格・月次減価償却・帳簿価額を確認", "Manage investment and fixed assets; view asset prices, monthly depreciation, and book value"),
    ("无法打开固定资产", "固定資産を開けません", "Could not open fixed assets"),
    ("无法打开登记窗口", "登録画面を開けません", "Could not open the registration window"),
    ("操作失败", "操作に失敗しました", "Action failed"),
    ("按购入月份和预计使用月数计算直线折旧，购入月份计为第1个月。折旧只用于资产负债表账面价值，不新增利润表费用，也不改动原购买流水。报废后从报废月份起移出资产负债表；报废时剩余价值保留为参考信息。是否计入资产负债表，请在“家庭财务报表→资产负债表”中点击每项前的方框设置。", "購入月と使用予定月数に基づき定額法で減価償却します。購入月を1か月目として数えます。減価償却は貸借対照表の帳簿価額にのみ反映し、損益計算書の費用や購入取引は変更しません。廃棄後は廃棄月から貸借対照表に計上せず、廃棄時の残存価額は参考情報として保持します。貸借対照表に含めるかどうかは、「家庭財務レポート→貸借対照表」で各項目の前にあるチェックボックスをクリックして設定します。", "Straight-line depreciation is based on the purchase month and useful life in months; the purchase month counts as month one. Depreciation changes the balance-sheet book value only. It does not add an income-statement expense or change the purchase transaction. Disposed assets leave the balance sheet starting in the disposal month, while their remaining value is kept for reference. To include an asset on the balance sheet, click the box before it under Family Financial Reports → Balance Sheet."),
    ("资产名称", "資産名", "Asset name"),
    ("购入月份", "購入月", "Purchase month"),
    ("购入金额", "購入金額", "Purchase cost"),
    ("每月折旧", "毎月の減価償却", "Monthly depreciation"),
    ("预计使用", "使用予定", "Useful life"),
    ("累计折旧", "減価償却累計額", "Accumulated depreciation"),
    ("剩余账面价值", "帳簿価額残高", "Remaining book value"),
    ("折旧进度", "減価償却の進捗", "Depreciation progress"),
    ("计入B/S", "貸借対照表に計上", "On balance sheet"),
    ("状态", "状態", "Status"),
    ("选中资产的折旧情况", "選択した資産の減価償却状況", "Depreciation for selected asset"),
    ("计入", "計上", "Include"),
    ("{elapsed}/{life}个月 · {percent}%", "{elapsed}/{life}か月 · {percent}%", "{elapsed}/{life} months · {percent}%"),
    ("每月折旧：{monthly}　累计折旧：{depreciated}　剩余账面价值：{remaining}　购入原值：{cost}", "毎月の減価償却：{monthly}　減価償却累計額：{depreciated}　帳簿価額残高：{remaining}　取得原価：{cost}", "Monthly depreciation: {monthly}　Accumulated depreciation: {depreciated}　Remaining book value: {remaining}　Original cost: {cost}"),
    ("报废月份：{month}；该月起不计入资产负债表。", "廃棄月：{month}。その月から貸借対照表に計上しません。", "Disposal month: {month}; excluded from the balance sheet starting that month."),
    ("请选择一项固定资产查看折旧进度。", "資産を選択すると減価償却の進捗を確認できます。", "Select a fixed asset to view its depreciation progress."),
    ("尚未购入", "未購入", "Not yet acquired"),
    ("已报废", "廃棄済み", "Disposed"),
    ("使用中", "使用中", "In use"),
    ("{months}个月", "{months}か月", "{months} months"),
    ("{percent}% · {elapsed}/{life}", "{percent}% · {elapsed}/{life}", "{percent}% · {elapsed}/{life}"),
    ("是", "はい", "Yes"),
    ("否", "いいえ", "No"),
    ("共登记 {count} 项；截至 {month} 的进度按月份计算。", "登録資産は{count}件です。{month}時点の進捗は月単位で計算します。", "{count} assets registered; progress is calculated by month through {month}."),
    ("编辑固定资产", "固定資産を編集", "Edit fixed asset"),
    ("登记固定资产", "固定資産を登録", "Register fixed asset"),
    ("购入月份（支持202608、8月）", "購入月（202608、2026-08などに対応）", "Purchase month (e.g. 202608 or 2026-08)"),
    ("购入月份格式无效。支持 YYYY-MM、YYYYMM、M月或完整日期。", "購入月の形式が無効です。YYYY-MM、YYYYMM、M月、または完全な日付を入力してください。", "Invalid purchase month. Use YYYY-MM, YYYYMM, M月, or a full date."),
    ("币种", "通貨", "Currency"),
    ("预计使用月数", "使用予定月数", "Useful life in months"),
    ("报废月份（可留空，支持202608、8月）", "廃棄月（空欄可、202608、2026-08などに対応）", "Disposal month (optional; e.g. 202608 or 2026-08)"),
    ("报废月份格式无效。支持 YYYY-MM、YYYYMM、M月或完整日期。", "廃棄月の形式が無効です。YYYY-MM、YYYYMM、M月、または完全な日付を入力してください。", "Invalid disposal month. Use YYYY-MM, YYYYMM, M月, or a full date."),
    ("报废月份", "廃棄月", "Disposal month"),
    ("金额按该币种最小单位存储；月度舍入差额会在使用期内分配，累计折旧不会超过原值。", "金額は通貨の最小単位で保存します。月ごとの丸め差は使用期間に配分し、減価償却累計額が取得原価を超えないようにします。", "Amounts are stored in the currency's smallest unit. Rounding differences are distributed over the useful life, and accumulated depreciation never exceeds original cost."),
    ("预计使用月数必须是整数", "使用予定月数は整数で入力してください", "Useful life must be a whole number of months"),
    ("固定资产名称不能为空", "固定資産名は必須です", "Enter an asset name"),
    ("购入金额必须大于0", "購入金額は0より大きくしてください", "Purchase cost must be greater than zero"),
    ("购入金额超出账本可保存范围", "購入金額が台帳の保存上限を超えています", "Purchase cost exceeds the ledger's storage limit"),
    ("预计使用月数必须在1到1200之间", "使用予定月数は1～1200か月で入力してください", "Useful life must be between 1 and 1,200 months"),
    ("报废月份不能早于购入月份", "廃棄月は購入月より前にできません", "Disposal month cannot be before the purchase month"),
    ("更新失败", "更新に失敗しました", "Update failed"),
    ("请选择资产", "資産を選択してください", "Select an asset"),
    ("请先选择一项固定资产。", "固定資産を選択してください。", "Select a fixed asset first."),
    ("资产已报废", "資産は廃棄済みです", "Asset already disposed"),
    ("该资产已标记为报废月份 {month}；如需修改，请编辑资产记录。", "この資産は廃棄月{month}として登録済みです。変更する場合は資産記録を編集してください。", "This asset is marked as disposed in {month}. Edit the asset record to change it."),
    ("无法报废", "廃棄できません", "Cannot mark as disposed"),
    ("报废月份不能早于购入月份。", "廃棄月は購入月より前にできません。", "The disposal month cannot precede the purchase month."),
    ("确认标记报废", "廃棄の確認", "Confirm disposal"),
    ("将“{name}”标记为 {month} 报废。该月起从资产负债表移除；报废时剩余账面价值仅保留参考，不会自动记入利润表。", "「{name}」を{month}に廃棄したものとして登録します。その月から貸借対照表から除外します。廃棄時の帳簿価額は参考情報として保持し、損益計算書には自動計上しません。", "Mark “{name}” as disposed in {month}. It will be removed from the balance sheet starting that month. Its remaining book value is kept for reference and is not automatically entered as an income-statement expense."),
    ("删除固定资产登记", "固定資産の登録を削除", "Delete fixed-asset record"),
    ("只删除该资产登记和折旧进度，不会删除或改写原有购买流水。", "資産登録と減価償却の進捗だけを削除します。元の購入取引は削除・変更しません。", "Only the asset record and depreciation progress will be deleted. The original purchase transaction will remain unchanged."),
    ("＋ 登记固定资产", "＋ 固定資産を登録", "+ Register asset"),
    ("编辑选中项", "選択項目を編集", "Edit selected"),
    ("设为本月报废", "今月廃棄として登録", "Mark disposed this month"),
    ("删除登记", "登録を削除", "Delete record"),
    ("当前记账请求完成后再管理固定资产。", "現在の記帳リクエスト完了後に固定資産を管理してください。", "Manage fixed assets after the current bookkeeping request finishes."),
    ("预算管理", "予算管理", "Budget Management"),
    ("查看本期消费并设置分类预算", "今期の支出を確認し、分類別予算を設定", "Review this period's spending and set category budgets"),
    ("本期花费", "今期の支出", "Spending this period"),
    ("至", "～", "to"),
    ("已入账支出：", "記帳済み支出：", "Posted spending: "),
    ("按15日至次月14日账期；人民币使用交易日汇率折算，缺少汇率的流水不计入图表。", "毎月15日から翌月14日までの集計です。人民元は取引日の為替レートで換算し、レートがない取引はグラフに含めません。", "Uses the 15th-to-14th billing cycle. CNY is converted using the transaction-date rate; entries without a rate are excluded from charts."),
    ("每日消费趋势", "日別支出の推移", "Daily spending trend"),
    ("支出趋势", "支出の推移", "Spending trend"),
    ("日度按本期账期；月度看近12个月", "日別は今期の請求期間、月別は直近12か月を表示", "Daily shows this billing period; monthly shows the last 12 months"),
    ("日度", "日別", "Daily"),
    ("月度", "月別", "Monthly"),
    ("所选期间暂无已入账消费", "選択期間に確定済み支出はありません", "No posted spending in the selected period"),
    ("消费类别", "支出カテゴリ", "Spending category"),
    ("类别预算", "カテゴリ別予算", "Category budgets"),
    ("本期暂无已入账消费", "今期の確定支出はありません", "No posted spending this period"),
    ("本期暂无分类支出", "今期のカテゴリ別支出はありません", "No categorized spending this period"),
    ("编辑预算", "予算を編集", "Edit budget"),
    ("设置本期类别预算（JPY）", "今期のカテゴリ別予算を設定（JPY）", "Set category budgets for this period (JPY)"),
    ("新账期默认沿用月度预算；本期修改仅影响本期。", "新しい請求期間には月次予算を適用します。今期の変更は今期のみ有効です。", "New periods use the monthly template by default; edits here apply only to this period."),
    ("预算类别使用账本消费分类；旧预算类别会合并到对应类别，无法匹配的归入“其他”。", "予算には台帳の支出カテゴリを使います。以前の予算カテゴリは対応するカテゴリに統合し、一致しないものは「その他」にまとめます。", "Budgets use ledger spending categories. Legacy budget labels are merged into matching categories; unmatched labels go to Other."),
    ("本期预算（JPY）", "今期予算（JPY）", "Period budget (JPY)"),
    ("编辑所选预算", "選択した予算を編集", "Edit selected budget"),
    ("添加类别预算", "カテゴリ予算を追加", "Add category budget"),
    ("保存修改", "変更を保存", "Save changes"),
    ("取消编辑", "編集をキャンセル", "Cancel editing"),
    ("类别预算已存在", "カテゴリ予算は登録済みです", "Budget already exists"),
    ("该类别已有预算，请使用“编辑所选预算”修改。", "このカテゴリには予算があります。「選択した予算を編集」から変更してください。", "This category already has a budget. Use Edit selected budget to change it."),
    ("正在编辑：", "編集中：", "Editing: "),
    ("当前没有正在编辑的预算。", "編集中の予算はありません。", "No budget is currently being edited."),
    ("所编辑的类别预算已不存在，请取消编辑后重试。", "編集中のカテゴリ予算が見つかりません。編集をキャンセルして再試行してください。", "The budget being edited no longer exists. Cancel editing and try again."),
    ("保存/更新类别预算", "カテゴリ予算を保存／更新", "Save/update category budget"),
    ("删除所选预算", "選択した予算を削除", "Remove selected budget"),
    ("本期预算合计：", "今期予算合計：", "Total budget this period: "),
    ("预算 JPY", "予算 JPY", "Budget JPY"),
    ("已花费 JPY", "支出済み JPY", "Spent JPY"),
    ("预算余量 JPY", "予算残額 JPY", "Budget remaining JPY"),
    ("本期预算分配", "今期予算の配分", "Budget allocation this period"),
    ("添加类别预算后显示预算分配", "カテゴリ予算を追加すると配分を表示します", "Add category budgets to see the allocation"),
    ("类别预算均为0，暂无分配", "予算がすべて0のため、配分はありません", "All budgets are zero, so there is no allocation to show"),
    ("预算管理无法读取：", "予算管理を読み込めません：", "Could not load budget management: "),
    ("请输入有效的日元预算金额。", "有効な円の予算額を入力してください。", "Enter a valid JPY budget amount."),
    ("请先选择消费类别。", "支出カテゴリを選択してください。", "Select a spending category first."),
    ("未选择预算", "予算が選択されていません", "No budget selected"),
    ("请先选择要编辑的类别预算。", "編集するカテゴリ予算を選択してください。", "Select a category budget to edit."),
    ("请先选择要删除的类别预算。", "削除するカテゴリ予算を選択してください。", "Select a category budget to remove."),
    ("删除类别预算", "カテゴリ予算を削除", "Remove category budget"),
    ("只移除该类别本期预算设定，不会删除账务流水。", "このカテゴリの今期予算設定だけを削除します。取引記録は削除されません。", "Only this category's budget for the current period will be removed. Ledger entries will remain."),
    ("缺少交易日汇率，未计入图表的支出：", "取引日の為替レートがないため、グラフから除外した支出：", "Spending excluded from charts due to a missing transaction-date rate: "),
    ("笔", "件", "entries"),
    ("当前记账请求完成后再查看预算管理。", "現在の記帳リクエスト完了後に予算管理を確認してください。", "View budget management after the current bookkeeping request finishes."),
    ("GitHub 同步", "GitHub同期", "GitHub sync"),
    ("每笔记账后自动同步到 GitHub", "記帳後にGitHubへ自動同期", "Automatically sync to GitHub after each entry"),
    ("记账成功后在后台按上方选择范围上传数据。需要先连接 GitHub；多台设备的修改不会自动合并。", "記帳が成功すると、上で選択した範囲のデータをバックグラウンドでアップロードします。事前にGitHubへ接続してください。複数デバイスの変更は自動統合されません。", "After each successful entry, upload the data selected above in the background. Connect GitHub first; changes from multiple devices are not merged automatically."),
    ("GitHub 自动同步已开启。", "GitHub自動同期を有効にしました。", "GitHub auto-sync is on."),
    ("GitHub 自动同步已关闭。", "GitHub自動同期を無効にしました。", "GitHub auto-sync is off."),
    ("GitHub 自动同步设置无法读取。", "GitHub自動同期設定を読み込めません。", "Could not read the GitHub auto-sync setting."),
    ("自动同步设置无法保存：{error}", "自動同期設定を保存できません：{error}", "Could not save the auto-sync setting: {error}"),
    ("GitHub 自动同步无法启动：{error}", "GitHub自動同期を開始できません：{error}", "Could not start GitHub auto-sync: {error}"),
    ("账本已记录，正在自动同步到 GitHub…", "台帳を記録しました。GitHubへ自動同期しています…", "Entry saved. Syncing to GitHub…"),
    ("账本已记录并同步到 GitHub。", "台帳を記録し、GitHubへ同期しました。", "Entry saved and synced to GitHub."),
    ("账本已记录在本地；请先连接 GitHub，连接后会上传当前同步数据。", "台帳はこのPCに記録しました。先にGitHubへ接続してください。接続後に現在の同期データをアップロードします。", "Entry saved locally. Connect GitHub first; the current synced data will be uploaded when connected."),
    ("账本已记录在本地，但自动同步失败：{error}", "台帳はこのPCに記録しましたが、自動同期に失敗しました：{error}", "Entry saved locally, but automatic sync failed: {error}"),
    ("点击后先在浏览器安装 GitHub App，再完成设备授权。软件会在你的账号下使用独立私有仓库备份数据；密码只在 GitHub 页面输入。", "クリックすると、まずブラウザーでGitHub Appをインストールし、その後デバイス認証を行います。データはあなたのアカウント内の専用プライベートリポジトリにバックアップされます。パスワードはGitHubのページでのみ入力します。", "Click to install the GitHub App in your browser, then complete device authorization. Your data is backed up to a dedicated private repository in your account. Enter your password only on GitHub."),
    ("尚未连接 GitHub。点击下方按钮并在浏览器授权即可。", "GitHubに接続されていません。下のボタンをクリックし、ブラウザーで認証してください。", "GitHub is not connected. Click the button below and authorize in your browser."),
    ("GitHub App 尚未完成配置；软件开发者需先配置公开 Client ID。", "GitHub Appの設定が完了していません。開発者が公開Client IDを設定する必要があります。", "The GitHub App is not configured yet. The developer must set its public Client ID."),
    ("旧版 GitHub 授权需要更新；点击下方按钮重新连接。", "旧バージョンのGitHub認証を更新する必要があります。下のボタンから再接続してください。", "The older GitHub authorization needs updating. Reconnect with the button below."),
    ("已连接 GitHub：{repository}", "GitHubに接続済み：{repository}", "Connected to GitHub: {repository}"),
    ("云备份内容由上方勾选项决定。API 密钥、GitHub 授权、界面语言及本机偏好始终只保存在本机；同步包未额外加密。", "クラウドバックアップの内容は上で選択した項目に従います。APIキー、GitHub認証、画面言語、端末固有の設定はこのPCにのみ保存されます。同期パッケージ自体は追加で暗号化しません。", "Cloud backup contents follow the selections above. API keys, GitHub authorization, interface language, and device preferences stay on this device. The sync bundle is not additionally encrypted."),
    ("GitHub App 仅申请创建私有仓库及读写同步数据文件所需的权限；授权可在 GitHub 设置中撤销。", "GitHub Appはプライベートリポジトリの作成と同期データファイルの読み書きに必要な権限のみを要求します。認証はGitHubの設定から取り消せます。", "The GitHub App requests only the permissions needed to create a private repository and read or write the sync data file. You can revoke authorization in GitHub settings."),
    ("当前同步整份快照，不会自动合并两台设备各自的修改；一台上传后，另一台应从 GitHub 恢复。", "現在はスナップショット全体を同期し、2台の変更を自動統合しません。一方のPCからアップロードした後、もう一方はGitHubから復元してください。", "Sync currently replaces the full snapshot and does not merge changes from two devices. After uploading from one device, restore from GitHub on the other."),
    ("GitHub 设置无法读取：{error}", "GitHub設定を読み込めません：{error}", "Could not read GitHub settings: {error}"),
    ("GitHub 设置不完整", "GitHub設定が未入力です", "GitHub settings are incomplete"),
    ("GitHub App 尚未配置", "GitHub Appが未設定です", "GitHub App is not configured"),
    ("GitHub App 尚未配置公开 Client ID；请由软件开发者完成应用配置。", "GitHub Appの公開Client IDが未設定です。ソフトウェア開発者による設定が必要です。", "The public GitHub App Client ID is not configured. The software developer must finish the app setup."),
    ("需要重新连接 GitHub", "GitHubへの再接続が必要です", "Reconnect to GitHub"),
    ("连接 GitHub", "GitHubに接続", "Connect to GitHub"),
    ("安装 GitHub App", "GitHub Appをインストール", "Install the GitHub App"),
    ("先把 Household Bookkeeping Sync Test 安装到你准备用来同步的 GitHub 账号。安装和设备授权是两步；如果已经安装，可直接继续。", "まず、同期に使うGitHubアカウントにHousehold Bookkeeping Sync Testをインストールしてください。インストールとデバイス認証は別の手順です。すでにインストール済みの場合は、そのまま続行できます。", "First install Household Bookkeeping Sync Test on the GitHub account you want to sync with. Installation and device authorization are separate steps. If it is already installed, continue."),
    ("安装时请核对 Contents 读写和 Repository creation 写入权限。安装完成后回到这里继续授权；软件只会在该账号的私有仓库中保存同步数据。", "インストール時にContentsの読み書きとRepository creationの書き込み権限を確認してください。完了したらここに戻って認証を続けます。同期データはそのアカウントのプライベートリポジトリにのみ保存されます。", "During installation, check for Contents read/write and Repository creation write permissions. Return here after installation to continue authorization. The app stores synced data in a private repository on that account."),
    ("打开 GitHub App 安装页", "GitHub Appのインストールページを開く", "Open GitHub App installation page"),
    ("已安装，继续授权", "インストール済み、認証を続ける", "Installed; continue to authorization"),
    ("无法打开 GitHub 安装页面", "GitHubインストールページを開けません", "Could not open the GitHub installation page"),
    ("无法打开 GitHub 安装页面：{error}", "GitHubインストールページを開けません：{error}", "Could not open the GitHub installation page: {error}"),
    ("GitHub App 尚未安装到当前账号，或安装权限尚未生效。请在软件的 GitHub 同步设置中打开 App 安装页，确认使用当前账号安装，并批准 Repository creation 和 Contents 权限，然后重新连接。", "GitHub Appが現在のアカウントにインストールされていないか、インストール権限がまだ有効になっていません。ソフトのGitHub同期設定からAppインストールページを開き、現在のアカウントにインストールされていることを確認し、Repository creationとContentsの権限を承認してから再接続してください。", "The GitHub App is not installed on this account, or its installation permissions are not active yet. Open the App installation page from GitHub sync settings, install it on the account currently in use, approve Repository creation and Contents permissions, then reconnect."),
    ("正在请求 GitHub 授权码…", "GitHub認証コードを取得しています…", "Requesting a GitHub authorization code…"),
    ("打开 GitHub 授权页面", "GitHub認証ページを開く", "Open GitHub authorization page"),
    ("复制验证码", "認証コードをコピー", "Copy verification code"),
    ("选择登录后的账本", "ログイン後の台帳を選択", "Choose the ledger after sign-in"),
    ("GitHub 已连接。请选择下载云端账本，或保留本机账本。下载会替换本机账本，恢复前会完整备份；保留本机后，自动下载将暂停，直到你手动从云端恢复。", "GitHubに接続しました。クラウドの台帳を取得するか、この端末の台帳を保持するか選択してください。取得すると完全バックアップ後に台帳を置き換えます。保持を選ぶと手動で復元するまで自動取得を停止します。", "GitHub is connected. Download the cloud ledger or keep this device's ledger. Downloading replaces this ledger after a full backup. Keeping local pauses automatic downloads until you manually restore from the cloud."),
    ("下载云端账本", "クラウドの台帳を取得", "Download cloud ledger"),
    ("保留本机账本", "この端末の台帳を保持", "Keep local ledger"),
    ("已保留本机账本，自动下载已暂停。", "この端末の台帳を保持し、自動取得を停止しました。", "Local ledger kept. Automatic downloads are paused."),
    ("已复制", "コピーしました", "Copied"),
    ("复制失败，请重试", "コピーできませんでした。再試行してください", "Copy failed; try again"),
    ("取消", "キャンセル", "Cancel"),
    ("请打开 GitHub 授权页面并输入下面的验证码。授权完成后会自动连接私有仓库。", "GitHub認証ページを開き、次のコードを入力してください。認証後、プライベートリポジトリに接続します。", "Open the GitHub authorization page and enter this code. The private repository will be connected after authorization."),
    ("连接 GitHub 并备份", "GitHubに接続してバックアップ", "Connect GitHub and back up"),
    ("等待在浏览器中完成 GitHub 授权…", "ブラウザーでのGitHub認証を待っています…", "Waiting for GitHub authorization in the browser…"),
    ("GitHub 已连接，私有仓库已创建并上传本机同步数据。", "GitHubに接続し、プライベートリポジトリを作成してこのPCの同期データをアップロードしました。", "GitHub is connected. A private repository was created and this device's synced data was uploaded."),
    ("GitHub 已连接，同步文件已首次上传。", "GitHubに接続し、同期ファイルを初めてアップロードしました。", "GitHub is connected, and the sync file was uploaded for the first time."),
    ("已连接 GitHub；该私有仓库已有数据，请选择上传或恢复。", "GitHubに接続しました。このプライベートリポジトリにはデータがあります。アップロードまたは復元を選択してください。", "Connected to GitHub. This private repository already has data; choose whether to upload or restore."),
    ("GitHub 连接失败：{error}", "GitHubに接続できません：{error}", "GitHub connection failed: {error}"),
    ("GitHub 数据同步失败：{error}", "GitHubデータ同期に失敗しました：{error}", "GitHub data sync failed: {error}"),
    ("GitHub 云端同步文件已在其他设备更新，本次上传已取消，云端数据未被覆盖。请先从 GitHub 恢复，或确认后手动上传本机数据。", "GitHubの同期ファイルが別のデバイスで更新されたため、今回のアップロードを中止しました。クラウドのデータは上書きされていません。先にGitHubから復元するか、確認のうえ手動でこのPCのデータをアップロードしてください。", "The GitHub sync file was updated on another device, so this upload was canceled. Cloud data was not overwritten. Restore from GitHub first, or explicitly upload this device's data."),
    ("GitHub 云端同步文件已发生变化，本次上传未覆盖云端数据。请重新同步后再试。", "GitHubの同期ファイルが変更されたため、今回のアップロードではクラウドのデータを上書きしませんでした。同期し直してから再試行してください。", "The GitHub sync file changed. This upload did not overwrite cloud data. Sync again and retry."),
    ("下载期间 GitHub 云端同步文件发生变化，请重新恢复。", "ダウンロード中にGitHubの同期ファイルが変更されました。もう一度復元してください。", "The GitHub sync file changed during download. Please restore again."),
    ("GitHub 连接失败", "GitHub接続エラー", "GitHub connection failed"),
    ("GitHub 同步失败", "GitHub同期エラー", "GitHub sync failed"),
    ("尚未连接 GitHub", "GitHubに接続されていません", "GitHub is not connected"),
    ("请先授权并连接 GitHub。", "先にGitHubを認証して接続してください。", "Authorize and connect GitHub first."),
    ("上传本机数据", "このPCのデータをアップロード", "Upload this device's data"),
    ("从 GitHub 恢复并重启", "GitHubから復元して再起動", "Restore from GitHub and restart"),
    ("将本机同步范围内的数据写入 GitHub，并覆盖云端当前同步文件。GitHub 会保留每次提交的历史版本。继续吗？", "このPCの同期対象データをGitHubに書き込み、現在の同期ファイルを置き換えます。GitHubには各コミットの履歴が残ります。続行しますか？", "Write this device's synced data to GitHub, replacing the current cloud sync file. GitHub retains each committed version. Continue?"),
    ("从 GitHub 恢复", "GitHubから復元", "Restore from GitHub"),
    ("将用 GitHub 数据替换本机账本、支付规则、自定义 Skill 和已保存的小票图片。API 配置、GitHub 授权、界面语言等本机设置保持不变。恢复前会自动备份本机同步数据，完成后软件将重启。继续吗？", "GitHubのデータでこのPCの台帳、支払ルール、カスタムSkill、保存済みレシート画像を置き換えます。API設定、GitHub認証、画面言語など端末固有の設定は変更しません。復元前に同期対象データを自動バックアップし、完了後にソフトを再起動します。続行しますか？", "Replace this device's ledger, payment rules, custom skills, and saved receipt images with GitHub data. Local settings such as API configuration, GitHub authorization, and interface language stay unchanged. Synced data is backed up first, and the app will restart after restore. Continue?"),
    ("正在打包并上传本机数据…", "このPCのデータを圧縮してアップロードしています…", "Packaging and uploading this device's data…"),
    ("正在下载并校验云端数据…", "クラウドデータをダウンロードして確認しています…", "Downloading and validating cloud data…"),
    ("本机同步数据已上传到 GitHub。", "このPCの同期データをGitHubにアップロードしました。", "This device's synced data was uploaded to GitHub."),
    ("云端数据已恢复。本机恢复前备份：{path}。软件即将重启。", "クラウドデータを復元しました。復元前バックアップ：{path}。ソフトを再起動します。", "Cloud data was restored. Backup from before restore: {path}. The app will restart."),
    ("恢复完成", "復元完了", "Restore complete"),
    ("同步完成", "同期完了", "Sync complete"),
    ("GitHub 授权已失效；请重新连接 GitHub。", "GitHub認証の有効期限が切れました。GitHubに再接続してください。", "GitHub authorization expired. Connect to GitHub again."),
    ("GitHub 授权已过期，请重新连接 GitHub。", "GitHub認証の有効期限が切れました。GitHubに再接続してください。", "GitHub authorization expired. Connect to GitHub again."),
    ("GitHub 仓库或同步文件不存在。", "GitHubリポジトリまたは同期ファイルが見つかりません。", "The GitHub repository or sync file was not found."),
    ("GitHub 仓库中还没有同步数据。", "GitHubリポジトリに同期データがありません。", "There is no synced data in the GitHub repository yet."),
    ("无法连接 GitHub；请检查网络连接后重试。", "GitHubに接続できません。ネットワークを確認して再試行してください。", "Could not connect to GitHub. Check the network and try again."),
    ("GitHub 返回了无法识别的响应。", "GitHubから認識できない応答が返されました。", "GitHub returned an unrecognized response."),
    ("GitHub 返回的数据无法读取。", "GitHubから返されたデータを読み取れません。", "Could not read the response from GitHub."),
    ("GitHub 拒绝了请求，请检查授权权限或请求频率。", "GitHubがリクエストを拒否しました。権限またはリクエスト頻度を確認してください。", "GitHub rejected the request. Check the authorization permissions or request rate."),
    ("同步包超过 60 MB；请减少小票图片后重试。", "同期パッケージが60 MBを超えています。レシート画像を減らして再試行してください。", "The sync bundle exceeds 60 MB. Remove some receipt images and try again."),
    ("恢复前本机备份超过 512 MB，无法安全继续恢复。", "復元前のローカルバックアップが512 MBを超えているため、安全に復元を続行できません。", "The local pre-restore backup exceeds 512 MB, so restore cannot safely continue."),
    ("GitHub 同步包超过 60 MB，无法下载。", "GitHubの同期パッケージが60 MBを超えているためダウンロードできません。", "The GitHub sync bundle exceeds 60 MB and cannot be downloaded."),
    ("同步包包含无效文件路径，已拒绝恢复。", "同期パッケージに無効なファイルパスがあるため、復元を中止しました。", "Restore was rejected because the sync bundle contains an invalid file path."),
    ("同步包解压后超过 512 MB，已拒绝恢复。", "展開後の同期パッケージが512 MBを超えるため、復元を中止しました。", "Restore was rejected because the unpacked sync bundle exceeds 512 MB."),
    ("同步包包含不支持的文件，已拒绝恢复。", "同期パッケージに未対応のファイルが含まれているため、復元を中止しました。", "Restore was rejected because the sync bundle contains an unsupported file."),
    ("GitHub 同步包缺少账本或支付规则。", "GitHub同期パッケージに台帳または支払ルールがありません。", "The GitHub sync bundle is missing the ledger or payment rules."),
    ("GitHub 同步包校验失败，当前本机账本保持不变。", "GitHub同期パッケージの検証に失敗しました。このPCの台帳は変更されていません。", "GitHub sync bundle validation failed. The local ledger has not changed."),
    ("GitHub 同步包清单无效或版本不兼容，当前本机账本保持不变。", "GitHub同期パッケージのマニフェストが無効か、バージョンに互換性がありません。このPCの台帳は変更されていません。", "The GitHub sync bundle manifest is invalid or incompatible. The local ledger has not changed."),
    ("GitHub 同步包支付规则文件无效或版本不兼容，当前本机账本保持不变。", "GitHub同期パッケージの支払ルールファイルが無効か、バージョンに互換性がありません。このPCの台帳は変更されていません。", "The GitHub sync bundle payment-rules file is invalid or incompatible. The local ledger has not changed."),
    ("GitHub 同步包账本数据库无法读取或完整性检查失败，当前本机账本保持不变。", "GitHub同期パッケージの台帳データベースを読み込めないか、整合性チェックに失敗しました。このPCの台帳は変更されていません。", "The ledger database in the GitHub sync bundle could not be read or failed its integrity check. The local ledger has not changed."),
    ("GitHub 授权等待超时，请重新连接。", "GitHub認証がタイムアウトしました。再接続してください。", "GitHub authorization timed out. Connect again."),
    ("GitHub 授权已取消。", "GitHub認証をキャンセルしました。", "GitHub authorization was canceled."),
    ("GitHub App 尚未启用 Device Flow；请由软件开发者检查 App 配置。", "GitHub AppでDevice Flowが有効になっていません。開発者がApp設定を確認してください。", "Device Flow is not enabled for the GitHub App. The software developer must check the app settings."),
    ("GitHub App Client ID 无效；请由软件开发者检查 App 配置。", "GitHub AppのClient IDが無効です。開発者がApp設定を確認してください。", "The GitHub App Client ID is invalid. The software developer must check the app settings."),
    ("GitHub 验证码无效或已过期，请重新连接。", "GitHub認証コードが無効または期限切れです。再接続してください。", "The GitHub verification code is invalid or expired. Connect again."),
    ("请先验证 GitHub 账号的主要邮箱，然后重新连接。", "GitHubアカウントのメインメールアドレスを確認してから、再接続してください。", "Verify the primary email address on your GitHub account, then connect again."),
    ("GitHub 刷新令牌已过期；请重新连接 GitHub。", "GitHubのリフレッシュトークンの有効期限が切れました。GitHubに再接続してください。", "The GitHub refresh token expired. Connect to GitHub again."),
    ("GitHub 授权码已过期，请重新连接。", "GitHub認証コードの有効期限が切れました。再接続してください。", "The GitHub authorization code expired. Connect again."),
    ("你拒绝了 GitHub 授权。", "GitHub認証を拒否しました。", "You denied GitHub authorization."),
    ("GitHub 同步设置无法读取；请重新连接 GitHub。", "GitHub同期設定を読み込めません。GitHubに再接続してください。", "Could not read GitHub sync settings. Reconnect to GitHub."),
    ("无法保存 GitHub 设置，请检查当前用户配置目录权限。", "GitHub設定を保存できません。ユーザー設定フォルダーのアクセス権を確認してください。", "Could not save GitHub settings. Check access to the current user's settings folder."),
    ("本地加密的 GitHub 令牌无法读取；请重新授权。", "暗号化されたGitHubトークンを読み込めません。再認証してください。", "Could not read the encrypted GitHub token. Authorize again."),
    ("GitHub 访问令牌为空，无法保存。", "GitHubアクセストークンが空のため保存できません。", "The GitHub access token is empty and cannot be saved."),
    ("无法保存 GitHub 令牌，请检查当前用户配置目录权限。", "GitHubトークンを保存できません。ユーザー設定フォルダーのアクセス権を確認してください。", "Could not save the GitHub token. Check access to the current user's settings folder."),
    ("无法开始 GitHub 授权。", "GitHub認証を開始できません。", "Could not start GitHub authorization."),
    ("GitHub 授权失败。", "GitHub認証に失敗しました。", "GitHub authorization failed."),
    ("请先连接 GitHub。", "先にGitHubに接続してください。", "Connect to GitHub first."),
    ("同名仓库已经存在且不是私有仓库；请换一个仓库名。", "同じ名前のリポジトリが存在しますが、プライベートではありません。別の名前を指定してください。", "A repository with that name already exists and is not private. Choose another name."),
    ("GitHub 同步包损坏或无法解压。", "GitHub同期パッケージが破損しているか、展開できません。", "The GitHub sync bundle is damaged or cannot be unpacked."),
    ("Gitee 同步", "Gitee同期", "Gitee sync"),
    ("使用自己的 Gitee 私有仓库备份。连接时需要在 Gitee 创建个人访问令牌；软件不会读取你的 Gitee 密码。", "自分のGiteeプライベートリポジトリにバックアップします。接続時にGiteeのパーソナルアクセストークンを作成します。ソフトはGiteeのパスワードを読み取りません。", "Back up to your own private Gitee repository. Create a Gitee personal access token to connect; the app never reads your Gitee password."),
    ("Gitee 自动同步已开启。", "Gitee自動同期を有効にしました。", "Gitee auto-sync is on."),
    ("Gitee 自动同步已关闭。", "Gitee自動同期を無効にしました。", "Gitee auto-sync is off."),
    ("Gitee 自动同步设置无法读取。", "Gitee自動同期設定を読み込めません。", "Could not read the Gitee auto-sync setting."),
    ("无法保存 Gitee 自动同步设置。", "Gitee自動同期設定を保存できません。", "Could not save the Gitee auto-sync setting."),
    ("Gitee 自动同步无法启动：{error}", "Gitee自動同期を開始できません：{error}", "Could not start Gitee auto-sync: {error}"),
    ("每笔记账后自动同步到 Gitee", "記帳後にGiteeへ自動同期", "Automatically sync to Gitee after each entry"),
    ("记账成功后在后台按上方选择范围上传数据。未连接时只保存本机；多台设备的修改不会自动合并。", "記帳が成功すると、上で選択した範囲のデータをバックグラウンドでアップロードします。未接続の場合はローカルにのみ保存され、複数端末の変更は自動統合されません。", "After each successful entry, upload the data selected above in the background. If Gitee is not connected, data stays local. Changes from multiple devices are not merged automatically."),
    ("Gitee 设置无法读取：{error}", "Gitee設定を読み込めません：{error}", "Could not read Gitee settings: {error}"),
    ("尚未连接 Gitee；点击下方按钮创建令牌并连接。", "Giteeに未接続です。下のボタンからトークンを作成して接続してください。", "Gitee is not connected. Create a token and connect using the button below."),
    ("已连接 Gitee：{repository}", "Giteeに接続済み：{repository}", "Connected to Gitee: {repository}"),
    ("云备份内容由上方勾选项决定；API 密钥、本机偏好、历史备份和 Gitee 令牌不上传。同步包未额外加密。Gitee 免费版单文件上限为 50 MB，本软件将同步包限制在 45 MiB。", "クラウドバックアップの内容は上で選択した項目に従います。APIキー、端末設定、過去のバックアップ、Giteeトークンはアップロードしません。同期パッケージ自体は暗号化されません。Gitee無料版の単一ファイル上限は50 MBのため、このソフトでは45 MiBに制限しています。", "Cloud backup contents follow the selections above. API keys, local preferences, backup history, and the Gitee token are excluded. The bundle itself is not encrypted. Gitee's free plan has a 50 MB per-file limit, so this app caps the bundle at 45 MiB."),
    ("Gitee 令牌权限较宽；创建时勾选 user_info 和 projects，仅在自己的设备保存，并可随时在 Gitee 撤销。多台设备不会自动合并；一台上传后，另一台应先恢复。", "Giteeトークンの権限は広いため、作成時にuser_infoとprojectsを選択し、自分の端末だけに保存してください。Giteeでいつでも取り消せます。複数端末の変更は自動統合されません。一方からアップロードした後、もう一方は先に復元してください。", "Gitee tokens have broad permissions. Select user_info and projects, save the token only on your own devices, and revoke it from Gitee at any time. Devices do not merge changes automatically; restore on the other device after uploading."),
    ("连接 Gitee", "Giteeに接続", "Connect to Gitee"),
    ("先创建 Gitee 个人访问令牌，至少勾选 user_info 和 projects。令牌用于识别账号、创建私有仓库及读写备份文件。", "Giteeのパーソナルアクセストークンを作成し、少なくともuser_infoとprojectsを選択してください。トークンはアカウントの確認、プライベートリポジトリの作成、バックアップファイルの読み書きに使います。", "Create a Gitee personal access token and select at least user_info and projects. The token identifies your account and creates, reads, and writes the private backup repository."),
    ("打开 Gitee 令牌设置", "Giteeトークン設定を開く", "Open Gitee token settings"),
    ("粘贴访问令牌", "アクセストークンを貼り付け", "Paste access token"),
    ("显示", "表示", "Show"),
    ("Gitee 连接失败", "Gitee接続エラー", "Gitee connection failed"),
    ("Gitee 连接失败：{error}", "Giteeに接続できません：{error}", "Gitee connection failed: {error}"),
    ("缺少 Gitee 令牌", "Giteeトークンがありません", "Gitee token is missing"),
    ("请先创建并粘贴 Gitee 个人访问令牌。", "Giteeのパーソナルアクセストークンを作成して貼り付けてください。", "Create and paste a Gitee personal access token first."),
    ("正在连接 Gitee 并检查私有仓库…", "Giteeに接続し、プライベートリポジトリを確認しています…", "Connecting to Gitee and checking the private repository…"),
    ("已连接 Gitee；该私有仓库已有备份，请选择上传或恢复。", "Giteeに接続しました。このプライベートリポジトリにはバックアップがあります。アップロードまたは復元を選択してください。", "Connected to Gitee. This private repository already has a backup; choose whether to upload or restore."),
    ("Gitee 已连接，私有仓库已创建并上传本机同步数据。", "Giteeに接続し、プライベートリポジトリを作成してこの端末の同期データをアップロードしました。", "Gitee is connected. A private repository was created and this device's synced data was uploaded."),
    ("Gitee 已连接，同步文件已首次上传。", "Giteeに接続し、同期ファイルを初めてアップロードしました。", "Gitee is connected, and the sync file was uploaded for the first time."),
    ("Gitee 未返回账户名称；请确认令牌有 user_info 权限。", "Giteeからアカウント名が返されませんでした。トークンにuser_info権限があることを確認してください。", "Gitee did not return an account name. Check that the token has user_info permission."),
    ("Gitee 令牌无效或权限不足；请重新生成令牌并勾选 user_info 与 projects 权限。", "Giteeトークンが無効か権限が不足しています。user_infoとprojects権限を選択してトークンを再作成してください。", "The Gitee token is invalid or lacks permissions. Create a new token with user_info and projects selected."),
    ("Gitee 令牌无效或没有读取私有仓库的权限。", "Giteeトークンが無効か、プライベートリポジトリを読む権限がありません。", "The Gitee token is invalid or cannot read the private repository."),
    ("请先创建令牌并连接 Gitee。", "先にトークンを作成してGiteeに接続してください。", "Create a token and connect to Gitee first."),
    ("尚未连接 Gitee", "Giteeに未接続です", "Gitee is not connected"),
    ("请先创建并粘贴 Gitee 个人访问令牌。", "Giteeのパーソナルアクセストークンを作成して貼り付けてください。", "Create and paste a Gitee personal access token first."),
    ("同名 Gitee 仓库已存在且不是私有仓库；请先改名或设为私有。", "同じ名前のGiteeリポジトリが存在しますが、プライベートではありません。名前を変更するか、非公開にしてください。", "A Gitee repository with that name already exists and is not private. Rename it or make it private first."),
    ("Gitee 同步设置无法读取；请重新连接 Gitee。", "Gitee同期設定を読み込めません。Giteeに再接続してください。", "Could not read Gitee sync settings. Connect to Gitee again."),
    ("无法保存 Gitee 设置，请检查当前用户配置目录权限。", "Gitee設定を保存できません。ユーザー設定フォルダーのアクセス権を確認してください。", "Could not save Gitee settings. Check access to the current user's settings folder."),
    ("本地加密的 Gitee 令牌无法读取；请重新连接。", "暗号化されたGiteeトークンを読み込めません。再接続してください。", "Could not read the encrypted Gitee token. Connect again."),
    ("Gitee 访问令牌为空，无法保存。", "Giteeアクセストークンが空のため保存できません。", "The Gitee access token is empty and cannot be saved."),
    ("无法保存 Gitee 令牌，请检查当前用户配置目录权限。", "Giteeトークンを保存できません。ユーザー設定フォルダーのアクセス権を確認してください。", "Could not save the Gitee token. Check access to the current user's settings folder."),
    ("请先连接 Gitee。", "先にGiteeに接続してください。", "Connect to Gitee first."),
    ("Gitee 返回了无法识别的响应。", "Giteeから認識できない応答が返されました。", "Gitee returned an unrecognized response."),
    ("Gitee 仓库或同步文件不存在。", "Giteeリポジトリまたは同期ファイルが見つかりません。", "The Gitee repository or sync file was not found."),
    ("Gitee 云端同步文件已发生变化，本次上传未覆盖云端数据。请先恢复云端数据或再次手动上传。", "Giteeの同期ファイルが変更されたため、今回のアップロードではクラウドデータを上書きしませんでした。先に復元するか、手動アップロードを再実行してください。", "The Gitee sync file changed, so this upload did not overwrite cloud data. Restore from the cloud or upload manually again."),
    ("Gitee 拒绝了过大的同步文件；请减少小票图片后重试。", "同期ファイルが大きすぎるためGiteeに拒否されました。レシート画像を減らして再試行してください。", "Gitee rejected the sync file because it is too large. Remove some receipt images and try again."),
    ("Gitee 请求失败（HTTP {code}）。", "Giteeリクエストに失敗しました（HTTP {code}）。", "Gitee request failed (HTTP {code})."),
    ("无法连接 Gitee；请检查网络连接后重试。", "Giteeに接続できません。ネットワークを確認して再試行してください。", "Could not connect to Gitee. Check the network and try again."),
    ("Gitee 返回的数据无法读取。", "Giteeから返されたデータを読み取れません。", "Could not read the response from Gitee."),
    ("Gitee 同步包超过 45 MiB，无法下载。", "Gitee同期パッケージが45 MiBを超えているためダウンロードできません。", "The Gitee sync bundle exceeds 45 MiB and cannot be downloaded."),
    ("Gitee 仓库中还没有账本备份。", "Giteeリポジトリに台帳バックアップがありません。", "There is no ledger backup in the Gitee repository yet."),
    ("下载 Gitee 账本失败（HTTP {code}）。", "Gitee台帳のダウンロードに失敗しました（HTTP {code}）。", "Could not download the Gitee ledger (HTTP {code})."),
    ("Gitee 未返回同步文件版本编号。", "Giteeから同期ファイルのバージョン番号が返されませんでした。", "Gitee did not return a sync-file revision."),
    ("Gitee 同步包超过 45 MiB；请减少小票图片后重试。", "Gitee同期パッケージが45 MiBを超えています。レシート画像を減らして再試行してください。", "The Gitee sync bundle exceeds 45 MiB. Remove some receipt images and try again."),
    ("Gitee 云端同步文件已在其他设备更新，本次上传已取消，云端数据未被覆盖。请先从 Gitee 恢复，或确认后手动上传本机数据。", "Giteeの同期ファイルが別の端末で更新されたため、今回のアップロードを中止しました。クラウドデータは上書きされていません。先にGiteeから復元するか、確認のうえ手動アップロードしてください。", "The Gitee sync file was updated on another device, so this upload was canceled and cloud data was not overwritten. Restore from Gitee first or explicitly upload this device's data."),
    ("请先从 Gitee 恢复，或确认后手动上传本机数据。", "先にGiteeから復元するか、確認のうえこの端末のデータを手動でアップロードしてください。", "Restore from Gitee first, or explicitly upload this device's data."),
    ("Gitee 未确认同步文件的版本编号；请重新读取云端版本。", "Giteeが同期ファイルのバージョン番号を確認できませんでした。クラウドのバージョンを再読み込みしてください。", "Gitee did not confirm the sync-file revision. Read the cloud revision again."),
    ("下载期间 Gitee 云端同步文件发生变化，请重新恢复。", "ダウンロード中にGiteeの同期ファイルが変更されました。もう一度復元してください。", "The Gitee sync file changed during download. Please restore again."),
    ("账本已记录并同步到 Gitee。", "台帳を記録し、Giteeへ同期しました。", "Entry saved and synced to Gitee."),
    ("账本已记录在本地，但 Gitee 自动同步失败：{error}", "台帳はローカルに記録しましたが、Gitee自動同期に失敗しました：{error}", "Entry saved locally, but Gitee auto-sync failed: {error}"),
    ("Gitee 自动同步无法启动：{error}", "Gitee自動同期を開始できません：{error}", "Could not start Gitee auto-sync: {error}"),
    ("连接并备份", "接続してバックアップ", "Connect and back up"),
    ("Gitee 已连接，私有仓库已创建并上传本机同步数据。", "Giteeに接続し、プライベートリポジトリを作成してこの端末の同期データをアップロードしました。", "Gitee is connected. A private repository was created and this device's synced data was uploaded."),
    ("Gitee 已连接，同步文件已首次上传。", "Giteeに接続し、同期ファイルを初めてアップロードしました。", "Gitee is connected, and the sync file was uploaded for the first time."),
    ("Gitee 连接失败：{error}", "Giteeに接続できません：{error}", "Gitee connection failed: {error}"),
    ("记账或定期收支正在处理中，请等处理完成后再从 Gitee 恢复。", "記帳または定期収支を処理中です。完了してからGiteeから復元してください。", "A bookkeeping or recurring transaction is being processed. Wait until it finishes before restoring from Gitee."),
    ("从 Gitee 恢复", "Giteeから復元", "Restore from Gitee"),
    ("将本机同步范围内的数据写入 Gitee，并覆盖云端当前同步文件。Gitee 会保留仓库提交历史。继续吗？", "この端末の同期対象データをGiteeに書き込み、現在の同期ファイルを置き換えます。Giteeにはコミット履歴が残ります。続行しますか？", "Write this device's synced data to Gitee, replacing the current cloud sync file. Gitee retains repository commit history. Continue?"),
    ("将用 Gitee 数据替换本机账本、支付规则、自定义 Skill 和已保存的小票图片。API 配置、Gitee 令牌、界面语言等本机设置保持不变。恢复前会自动备份本机同步数据，完成后软件将重启。继续吗？", "Giteeのデータでこの端末の台帳、支払ルール、カスタムSkill、保存済みレシート画像を置き換えます。API設定、Giteeトークン、画面言語など端末固有の設定は変更しません。復元前に同期対象データを自動バックアップし、完了後にソフトを再起動します。続行しますか？", "Replace this device's ledger, payment rules, custom skills, and saved receipt images with Gitee data. Local settings such as API configuration, Gitee token, and interface language stay unchanged. Synced data is backed up first, and the app will restart after restore. Continue?"),
    ("本机同步数据已上传到 Gitee。", "この端末の同期データをGiteeにアップロードしました。", "This device's synced data was uploaded to Gitee."),
    ("Gitee 数据同步失败：{error}", "Giteeデータの同期に失敗しました：{error}", "Gitee data sync failed: {error}"),
    ("Gitee 同步失败", "Gitee同期エラー", "Gitee sync failed"),
    ("连接 Gitee 并备份", "Giteeに接続してバックアップ", "Connect Gitee and back up"),
    ("上传本机数据到 Gitee", "この端末のデータをGiteeにアップロード", "Upload this device's data to Gitee"),
    ("从 Gitee 恢复并重启", "Giteeから復元して再起動", "Restore from Gitee and restart"),
    ("云端同步包损坏或无法解压。", "クラウド同期パッケージが破損しているか、展開できません。", "The cloud sync bundle is damaged or cannot be unpacked."),
    ("云端同步包缺少账本或清单。", "クラウド同期パッケージに台帳またはマニフェストがありません。", "The cloud sync bundle is missing the ledger or manifest."),
    ("云端同步包清单无效或版本不兼容，当前本机账本保持不变。", "クラウド同期パッケージのマニフェストが無効か、バージョンに互換性がありません。この端末の台帳は変更されていません。", "The cloud sync bundle manifest is invalid or incompatible. The local ledger has not changed."),
    ("云端同步包付款方式文件无效或版本不兼容，当前本机账本保持不变。", "クラウド同期パッケージの支払方法ファイルが無効か、バージョンに互換性がありません。この端末の台帳は変更されていません。", "The payment-methods file in the cloud sync bundle is invalid or incompatible. The local ledger has not changed."),
    ("云端同步包账本数据库无法读取或完整性检查失败，当前本机账本保持不变。", "クラウド同期パッケージの台帳データベースを読み込めないか、整合性チェックに失敗しました。この端末の台帳は変更されていません。", "The ledger database in the cloud sync bundle could not be read or failed its integrity check. The local ledger has not changed."),
    ("云备份范围", "クラウドバックアップ範囲", "Cloud backup scope"),
    ("选择放入 GitHub/Gitee 云备份的数据。默认全部选中；取消勾选的内容不会上传。首次连接、手动上传和自动同步都使用这里的选择。", "GitHub/Giteeのクラウドバックアップに含めるデータを選択します。初期状態ではすべて選択されています。チェックを外した項目はアップロードされません。初回接続、手動アップロード、自動同期でこの選択を使います。", "Choose what to include in GitHub/Gitee cloud backups. Everything is selected by default; unchecked items are not uploaded. The selection applies to initial connection, manual uploads, and automatic sync."),
    ("设置内容（预算、类别与自定义 Skill）", "設定（予算、カテゴリ、カスタムSkill）", "Settings (budgets, categories, and custom skills)"),
    ("账单（流水与小票）", "取引（明細とレシート）", "Bills (entries and receipts)"),
    ("付款方式", "支払方法", "Payment methods"),
    ("定期付款", "定期支払い", "Recurring payments"),
    ("银行及资金账户", "銀行・資金口座", "Bank and cash accounts"),
    ("信用卡", "クレジットカード", "Credit cards"),
    ("资产管理", "資産管理", "Asset management"),
    ("全选", "すべて選択", "Select all"),
    ("云备份范围已保存。", "クラウドバックアップ範囲を保存しました。", "Cloud backup scope saved."),
    ("云备份范围设置无法读取：{error}", "クラウドバックアップ範囲を読み込めません：{error}", "Could not read cloud backup scope: {error}"),
    ("无法保存云备份范围：{error}", "クラウドバックアップ範囲を保存できません：{error}", "Could not save cloud backup scope: {error}"),
    ("至少选择一项云备份内容。", "クラウドバックアップ項目を1つ以上選択してください。", "Select at least one cloud backup item."),
    ("云备份范围设置格式无效。", "クラウドバックアップ範囲の設定形式が無効です。", "The cloud backup scope settings are invalid."),
    ("云备份范围“{key}”必须是布尔值。", "クラウドバックアップ範囲「{key}」は真偽値である必要があります。", "Cloud backup scope value “{key}” must be a boolean."),
    ("API 密钥、GitHub/Gitee 令牌、界面语言和本机偏好始终只保存在本机。账户未勾选但账单或计划需要关联时，会保留匿名账户名，不含原账户名和余额；设置未勾选但账单或计划需要类别时，会保留类别占位名，不含原类别名和翻译。恢复云端快照会替换本机账本；快照未包含的账本内容不会出现在恢复结果中。", "APIキー、GitHub/Giteeトークン、画面言語、端末固有の設定はこのPCにのみ保存されます。口座を選択せずに取引や予定をバックアップする場合、関連を保つ匿名口座名を残し、元の口座名と残高は含めません。設定を選択せずにカテゴリを使う取引や予定をバックアップする場合、カテゴリ名と翻訳を含めず、カテゴリの仮名を残します。クラウドスナップショットの復元では台帳を置き換えます。スナップショットに含まれない台帳データは復元後に表示されません。", "API keys, GitHub/Gitee tokens, interface language, and device preferences stay on this device. If bills or plans need accounts whose group is unchecked, an anonymous account name is kept without the original name or balance. If they need categories while settings are unchecked, placeholder categories are kept without original category names or translations. Restoring a cloud snapshot replaces the local ledger; ledger data absent from the snapshot will not appear after restore."),
    ("云端同步包缺少已勾选的付款方式。", "クラウド同期パッケージに選択済みの支払方法がありません。", "The cloud sync bundle is missing the selected payment methods."),
    ("将用 GitHub 云端快照替换本机账本；快照未包含的账本内容恢复后不会出现在本机。备份包中未包含的付款方式、Skill 和小票图片会保留本机现有内容。API 配置、GitHub 授权、界面语言等本机设置保持不变。恢复前会自动备份本机全部账本及可同步数据（不含密钥、令牌和本机偏好），完成后软件将重启。继续吗？", "GitHubのクラウドスナップショットでこのPCの台帳を置き換えます。スナップショットに含まれない台帳データは復元後に表示されません。バックアップに含まれない支払方法、Skill、レシート画像はこのPCの現在の内容を維持します。API設定、GitHub認証、画面言語などの端末設定は変更しません。復元前に台帳と同期可能なデータをすべてバックアップします（APIキー、トークン、端末固有の設定は含みません）。完了後にソフトを再起動します。続行しますか？", "Replace this device's ledger with the GitHub snapshot. Ledger data absent from the snapshot will not appear after restore. Payment methods, skills, and receipt images omitted from the bundle stay as they are locally. Local settings such as API configuration, GitHub authorization, and interface language remain unchanged. All local ledger and syncable data is backed up first; API keys, tokens, and device preferences are excluded. The app restarts after restore. Continue?"),
    ("将用 Gitee 云端快照替换本机账本；快照未包含的账本内容恢复后不会出现在本机。备份包中未包含的付款方式、Skill 和小票图片会保留本机现有内容。API 配置、Gitee 令牌、界面语言等本机设置保持不变。恢复前会自动备份本机全部账本及可同步数据（不含密钥、令牌和本机偏好），完成后软件将重启。继续吗？", "Giteeのクラウドスナップショットでこの端末の台帳を置き換えます。スナップショットに含まれない台帳データは復元後に表示されません。バックアップに含まれない支払方法、Skill、レシート画像はこの端末の現在の内容を維持します。API設定、Giteeトークン、画面言語など端末設定は変更しません。復元前に台帳と同期可能なデータをすべてバックアップします（APIキー、トークン、端末固有の設定は含みません）。完了後にソフトを再起動します。続行しますか？", "Replace this device's ledger with the Gitee snapshot. Ledger data absent from the snapshot will not appear after restore. Payment methods, skills, and receipt images omitted from the bundle stay as they are locally. Local settings such as API configuration, Gitee token, and interface language remain unchanged. All local ledger and syncable data is backed up first; API keys, tokens, and device preferences are excluded. The app restarts after restore. Continue?"),
)

# Mobile PWA labels share the desktop translation catalog for maintenance.
_ROWS += (
    ("显示或隐藏金额", "金額表示の切替", "Show or hide amounts"),
    ("添加信用卡", "カード追加", "Add credit card"),
    ("登记资产", "資産を登録", "Register asset"),
    ("添加 API 服务", "APIを追加", "Add API service"),
    ("创建备份", "バックアップ作成", "Create backup"),
    ("上移", "上へ", "Move up"),
    ("下移", "下へ", "Move down"),
    ("移除扣款来源", "引落元を削除", "Remove funding source"),
    ("手动记一笔", "手入力で記帳", "Manual entry"),
    ("搜索说明、账户或类别", "内容・口座・カテゴリを検索", "Search entries, accounts or categories"),
    ("搜索账单", "取引を検索", "Search transactions"),
    ("开始日期", "開始日", "Start date"),
    ("结束日期", "終了日", "End date"),
    ("主导航", "メインナビゲーション", "Main navigation"),
    ("暂时收起", "閉じる", "Dismiss"),
    ("总览", "概要", "Today"),
    ("更多", "その他", "More"),
    ("生活，有迹可循", "暮らしを、ていねいに", "A little more clarity"),
    ("正在载入你的账本…", "台帳を読み込み中…", "Loading your ledger…"),
    ("总净资产 · JPY", "総純資産 · JPY", "Total net assets · JPY"),
    ("我的账本", "マイ台帳", "My ledger"),
    ("人民币资产独立核算", "人民元資産は別集計", "CNY assets tracked separately"),
    ("记一笔", "記帳する", "Record"),
    ("查看账户", "口座を見る", "Accounts"),
    ("本期支出", "今期の支出", "Period spending"),
    ("本期收入", "今期の収入", "Period income"),
    ("含人民币参考汇率折算", "人民元の参考換算を含む", "Includes CNY reference conversion"),
    ("预算，还剩", "予算の残り", "Room in your budget"),
    ("已用", "使用済み", "Used"),
    ("预算", "予算", "Budget"),
    ("钱花在哪里", "支出の内訳", "Where it went"),
    ("报表", "レポート", "Reports"),
    ("最近记录", "最近の記録", "Latest activity"),
    ("全部", "すべて", "See all"),
    ("从第一笔开始记录生活", "最初の記帳から始めましょう", "Start with your first entry"),
    ("部分历史人民币记录缺少汇率，未计入合并报表。", "一部の過去の人民元取引は為替未登録のため合計に含まれません。", "Some historical CNY entries lack exchange rates and are excluded from combined totals."),
    ("记录后会在这里呈现", "記帳するとここに表示されます", "Your spending will appear here"),
    ("按日期、账户或说明查找最近2000条记录", "最近2000件を日付・口座・内容で検索", "Search the latest 2,000 entries by date, account or description"),
    ("资金账户", "資金口座", "Cash"),
    ("固定资产", "固定資産", "Property"),
    ("欠款为额度差额估算，不代表当月账单。还款仅记录转账，不操作银行。", "債務は利用枠の差による目安です。返済は台帳内の振替のみです。", "Debt is an estimate from credit availability. Repayments only record ledger transfers."),
    ("欠款估算", "債務の目安", "Estimated debt"),
    ("快照", "スナップショット", "Snapshot"),
    ("录入快照", "枠を入力", "Snapshot"),
    ("还款", "返済", "Repay"),
    ("恢复额度快照", "枠履歴を復元", "Restore snapshot"),
    ("应还计划", "返済予定", "Due plan"),
    ("暂停计划", "予定を停止", "Pause plan"),
    ("启用计划", "予定を有効化", "Enable plan"),
    ("先登记一张信用卡", "カードを追加してください", "Add your first credit card"),
    ("编辑", "編集", "Edit"),
    ("个月直线折旧", "か月の定額償却", "months straight-line depreciation"),
    ("已计入报表", "集計対象", "Included"),
    ("未计入报表", "集計対象外", "Excluded"),
    ("付款方式与扣款顺序", "支払ルールと優先順位", "Payment rules"),
    ("用途匹配，按账户顺序扣款", "用途と口座優先順位", "Scenarios and account priorities"),
    ("定期付款与收入", "定期支払・収入", "Recurring entries"),
    ("周期、账单币种与到期处理", "周期・請求通貨・期日処理", "Schedules, currencies and due dates"),
    ("预算与储蓄", "予算と貯蓄", "Budget & savings"),
    ("本期分配与消费趋势", "今期予算と支出推移", "Allocation and spending trends"),
    ("资产负债与15日至14日收支", "貸借・15日〜14日の損益", "Balance sheet and period activity"),
    ("食材与饮食健康", "食材と食生活", "Food & wellbeing"),
    ("采购、食用记录与回顾", "購入・食事記録・振り返り", "Purchases, meals and reviews"),
    ("备份与多设备恢复", "バックアップと復元", "Backup & restore"),
    ("GitHub、Gitee 与本机快照", "GitHub・Gitee・ローカル", "GitHub, Gitee and local snapshots"),
    ("收入、支出与三种显示语言", "収入・支出・表示名", "Income, expense and display names"),
    ("设置与 Agent Skill", "設定・Agent Skill", "Settings & agent skills"),
    ("API 服务、文本 Skill 与隐私", "API・Skillテキスト・プライバシー", "API services, text skills and privacy"),
    ("安装到 iPhone", "iPhoneにインストール", "Install on iPhone"),
    ("添加到主屏幕与离线使用", "ホーム画面・オフライン", "Home Screen and offline access"),
    ("‹ 更多", "‹ その他", "‹ More"),
    ("新增规则", "予定を追加", "New schedule"),
    ("处理到期项目", "期日を処理", "Process due entries"),
    ("启用", "有効化", "Enable"),
    ("报告截至日期", "レポート基準日", "Report through date"),
    ("本期收支", "今期の損益", "Period activity"),
    ("备查支出单独保留；信用卡负债为额度估算，转账不计作消费。", "メモ支出を区別し、カード債務は目安として表示。振替は支出に含みません。", "Memo expenses remain distinct. Credit debt is an estimate; transfers are excluded from spending."),
    ("编辑本期预算", "今期予算を編集", "Edit budget"),
    ("剩余", "残り", "Remaining"),
    ("最近30天 · JPY", "直近30日 · JPY", "Last 30 days · JPY"),
    ("人民币支出按交易日参考汇率计入日元报表；原币流水仍独立保存。", "人民元は取引日の参考レートで換算し、元通貨明細も保持します。", "CNY spending uses its transaction-date reference rate; original-currency entries remain separate."),
    ("添加采购", "購入を追加", "Add purchase"),
    ("记录饮食", "食事を記録", "Log meal"),
    ("采购计入偏好", "購入の計上設定", "Purchase preference"),
    ("饮食回顾", "食生活の振り返り", "Food review"),
    ("采购食品", "購入した食品", "Food purchases"),
    ("翻译", "表示名", "Translate"),
    ("让记账住进你的主屏幕", "ホーム画面に家計簿を", "A place on your Home Screen"),
    ("在 iPhone Safari 打开当前 HTTPS 地址。", "iPhoneのSafariでこのHTTPSアドレスを開きます。", "Open this HTTPS address in Safari on iPhone."),
    ("点“分享”，选择“添加到主屏幕”。", "共有から「ホーム画面に追加」を選択。", "Tap Share, then Add to Home Screen."),
    ("开启“作为网页 App 打开”（如有），再点“添加”。", "表示される場合はWebアプリとして開くを有効にし「追加」。", "Enable Open as Web App if shown, then tap Add."),
    ("同 Wi-Fi 测试时，电脑需保持开机并运行服务。离线可暂存手动账目；Agent 和云备份需要连接服务。", "同じWi-FiでのテストはPCとサービスの起動が必要です。オフラインでは手動取引を保存できます。", "For Wi-Fi testing, keep the computer and service running. Manual entries can be queued offline; agents and cloud backups need a connection."),
    ("下载本机测试证书", "テスト証明書を取得", "Download test certificate"),
    ("每日支出趋势", "毎日の支出", "Daily spending"),
    ("设置与自定义 Skill", "設定・カスタムSkill", "Settings & skills"),
    ("账单与小票", "取引・レシート", "Entries & receipts"),
    ("银行与资金账户", "銀行・資金口座", "Cash accounts"),
    ("备份范围", "バックアップ範囲", "Backup scope"),
    ("全选 / 取消全选", "全選択 / 解除", "Select / clear all"),
    ("记账后自动云备份", "記帳後に自動バックアップ", "Back up after recording"),
    ("应用备份设置", "設定を適用", "Apply backup settings"),
    ("API 密钥与 GitHub/Gitee 授权不包含在备份中。恢复会替换账本，恢复前自动保留完整副本。", "APIキーやGitHub/Gitee認証は含めません。復元前に現在の完全コピーを保存します。", "API keys and GitHub/Gitee authorization are excluded. Restoring replaces the ledger after making a full safety copy."),
    ("已连接", "接続済み", "Connected"),
    ("未连接", "未接続", "Not connected"),
    ("使用你自己账号下的独立私有仓库", "自分のアカウントの非公開リポジトリ", "A private repository in your own account"),
    ("连接 / 重新授权", "接続・再認証", "Connect / authorize"),
    ("上传备份", "アップロード", "Upload"),
    ("从云端恢复", "復元", "Restore"),
    ("断开", "切断", "Disconnect"),
    ("本机备份历史", "ローカル履歴", "Local backup history"),
    ("下载", "保存", "Download"),
    ("导入完整备份包", "バックアップを取り込む", "Restore a backup file"),
    ("已保存小票", "保存済みレシート", "Saved receipt"),
    ("确定继续吗？", "続行しますか？", "Continue?"),
    ("此操作需要连接电脑服务；内容还在当前编辑页。", "この操作にはサービスへの接続が必要です。入力は編集画面に残っています。", "This action needs the computer service. Your input remains in the editor."),
    ("操作未完成", "操作未完了", "Action did not complete"),
    ("后台操作已完成", "バックグラウンド処理が完了しました", "Background action completed"),
    ("打开 GitHub 验证页，输入下面的临时授权码。新设备还需要安装 App 到自己的账号。", "GitHubの認証画面でコードを入力してください。新しい端末では自分のアカウントへのAppインストールも必要です。", "Open GitHub verification and enter this temporary code. Install the app on your account if needed."),
    ("打开授权页", "認証を開く", "Open verification"),
    ("请先同步待处理记录。", "先に未同期の記録を同期してください。", "Sync pending entries first."),
    ("恢复文件：", "ファイルを復元：", "Restore file: "),
    ("当前账本会被替换，恢复前会创建完整备份。", "現在の台帳を置き換え、復元前の完全コピーを保存します。", "The current ledger will be replaced after a full safety backup."),
    ("已恢复", "復元しました", "Restored"),
    ("处理中…", "処理中…", "Working…"),
    ("自然地说，认真地记", "いつもの言葉で、ていねいに", "Your words. A clear record."),
    ("记账助手", "記帳アシスタント", "Ledger assistant"),
    ("新对话", "新しい会話", "New chat"),
    ("消息", "メッセージ", "Message"),
    ("文字与小票都可以", "テキストもレシートも", "Words or receipts"),
    ("中断", "中断", "Stop"),
    ("让生活，清楚一点", "暮らしを、少しクリアに", "A clearer picture of everyday life"),
    ("告诉我一笔收支，或拍下小票。信息不足时先确认，记录成功后再备份。", "収支を伝えるか、レシートを撮影してください。不明点は確認してから記帳します。", "Tell me about an entry, or photograph a receipt. Unclear details are checked before recording."),
    ("移除图片", "画像を削除", "Remove image"),
    ("最多5张图片", "画像は5枚までです", "Up to 5 images"),
    ("图片超过20MB", "画像が20MBを超えています", "Image exceeds 20 MB"),
    ("无法读取图片，请使用 JPEG、PNG 或 WebP", "JPEG・PNG・WebPを使用してください", "Use JPEG, PNG or WebP"),
    ("附图", "画像", "Images"),
    ("设置与 Skill", "設定とSkill", "Settings & skills"),
    ("编辑内容不会自动保存。点应用保留当前页，点确认保存并关闭；取消撤回尚未应用的修改。", "変更は自動保存されません。「適用」で保存し画面を維持、「確定」で保存して閉じます。", "Changes are not saved automatically. Apply saves and stays here; Done saves and closes. Cancel discards unapplied changes."),
    ("服务", "サービス", "Service"),
    ("名称", "名前", "Name"),
    ("接口完整地址", "エンドポイントURL", "Full endpoint URL"),
    ("模型标识", "モデルID", "Model ID"),
    ("API 密钥（留空保留已保存密钥）", "APIキー（空欄で既存を保持）", "API key (blank keeps saved key)"),
    ("思考模式（支持的服务）", "思考モード（対応API）", "Thinking mode (supported providers)"),
    ("文字服务", "テキスト用", "Text service"),
    ("图片服务", "画像用", "Image service"),
    ("请选择", "選択してください", "Choose a service"),
    ("Skill 文本 · 复制粘贴后编辑", "Skillテキスト・貼り付けて編集", "Skill text · paste and edit"),
    ("恢复默认", "初期値に戻す", "Restore default"),
    ("此文本会随该 Agent 的请求发送给你选择的模型服务。", "このテキストは選択したモデルへのリクエストに含まれます。", "This text is included in requests to the model service you select."),
    ("保存记账小票图片", "記帳画像を保存", "Save receipt images"),
    ("删除 API 服务：", "APIサービスを削除：", "Remove API service: "),
    ("保存设置后生效，使用它的 Agent 需要重新选择服务。", "設定保存後に反映され、Agentのサービスを再選択する必要があります。", "Takes effect when settings are saved. Reassign agents using this service."),
    ("设置已应用", "適用しました", "Settings applied"),
    ("用途决定何时使用；扣款顺序决定先用哪个账户。同一规则只使用同币种账户，积分可加入日元顺序。", "用途が適用場面を決め、口座順が引落優先順位を決めます。同一通貨のみ使用します。", "The purpose matches a scenario; the ordered accounts determine funding. Keep one currency per rule; points may join JPY orders."),
    ("规则", "ルール", "Rule"),
    ("从上到下依次扣款", "上から順に引き落とし", "Funding priority, top to bottom"),
    ("添加扣款来源", "引落元を追加", "Add funding source"),
    ("添加规则", "ルールを追加", "Add rule"),
    ("保存后不再自动匹配此用途。", "保存後、この用途を自動適用しません。", "After saving, this scenario will no longer match."),
    ("移除扣款来源：", "引落元を削除：", "Remove funding source: "),
    ("保存后不再从此项扣款。", "保存後、この項目から引き落としません。", "This source will no longer be used after saving."),
    ("备份已创建", "バックアップを作成しました", "Backup created"),
    ("私人令牌 · user_info 与 projects 权限", "個人トークン・user_infoとprojects権限", "Personal token · user_info and projects"),
    ("私有仓库名称", "非公開リポジトリ名", "Private repository name"),
    ("请先完成待同步记录", "先に未同期記録を同期してください", "Sync pending entries first"),
    ("上传可能替换云端快照；恢复会替换当前账本并先保留完整备份。断开连接只撤销本软件保存的授权。", "アップロードはクラウドを置換、復元は台帳を置換します。先に完全コピーを保存します。切断は保存済み認証を解除します。", "Uploads may replace the cloud snapshot. Restore replaces this ledger after a full safety copy. Disconnect removes the stored authorization."),
    ("请等待当前请求完成", "現在の処理をお待ちください", "Wait for the current request"),
    ("清空当前对话", "会話を消去", "Clear this conversation"),
    ("未完成的草稿和聊天显示会清除，已入账记录保留。", "未確定下書きと会話を消去します。記帳済み取引は保持します。", "Pending drafts and displayed chat will clear. Posted entries remain."),
    ("正在中断", "中断中", "Stopping…"),
    ("移除这张待发送图片", "送信前の画像を削除", "Remove this pending image"),
    ("该图片将不会发送。", "この画像は送信されません。", "This image will not be sent."),
    ("本期金额每月重填，空白不记账。只记录本地转账，不实际扣款。", "当月金額は毎月入力。空欄なら記帳しません。実際の銀行引落は行いません。", "Enter this period's amount each month. Blank amounts are not posted. No actual bank debit occurs."),
    ("额度快照历史", "利用枠履歴", "Credit snapshots"),
    ("信用卡流水", "カード取引", "Card activity"),
    ("移除较新的快照，保留账目；操作前会备份。", "新しい枠履歴を削除し取引は保持。先にバックアップします。", "Newer snapshots will be removed; entries stay. A backup is made first."),
    ("购入原值", "取得原価", "Acquisition cost"),
    ("计入资产负债表", "貸借対照表に含める", "Include in balance sheet"),
    ("报废月份（可空）", "除却月（任意）", "Disposal month (optional)"),
    ("删除前保存完整备份；已有流水保留。", "削除前に完全バックアップ。既存取引は保持。", "A full backup is made before deletion. Posted entries remain."),
    ("请先显示数字再调整", "先に数字を表示してください", "Show numbers before editing"),
    ("核对实际余额", "実残高を照合", "Reconcile balance"),
    ("实际余额", "実際の残高", "Actual balance"),
    ("删除账户：", "口座を削除：", "Delete account: "),
    ("关联流水或计划的账户不能删除。删除前会备份。", "取引・予定で使う口座は削除できません。先にバックアップします。", "Accounts referenced by entries or plans cannot be deleted. A backup is made first."),
    ("规则名称", "予定名", "Schedule name"),
    ("每隔几个周期", "間隔", "Interval"),
    ("到期项目已检查", "期日の確認が完了しました", "Due entries checked"),
    ("本期预算", "今期予算", "Period budget"),
    ("总预算 · JPY", "予算合計 · JPY", "Total budget · JPY"),
    ("储蓄目标 · JPY", "貯蓄目標 · JPY", "Savings goal · JPY"),
    ("添加食品采购", "食品の購入", "Food purchase"),
    ("每行一种食物；数量可写在 | 后面", "1行に1品。数量は | の後に記入", "One food per line; optional quantity after |"),
    ("餐次（可空）", "食事区分（任意）", "Meal (optional)"),
    ("备注（可空）", "メモ（任意）", "Note (optional)"),
    ("将采购食品计入已吃回顾（不生成食用流水）", "購入食品を食事回顧に含める（食事記録は作成しない）", "Count food purchases in food reviews (does not create meals)"),
    ("删除食品记录", "食品記録を削除", "Delete food record"),
    ("仅删除食品记录，不撤销财务流水；先备份。", "食品記録のみ削除し、財務取引は保持。先にバックアップします。", "Deletes the food record, keeping financial entries. A backup is made first."),
    ("日语显示名（可空）", "日本語表示名（任意）", "Japanese name (optional)"),
    ("英语显示名（可空）", "英語表示名（任意）", "English name (optional)"),
    ("类别显示名", "カテゴリ表示名", "Category display name"),
    ("显示名", "表示名", "Display name"),
    ("账单详情", "取引の詳細", "Entry details"),
    ("核对并确认", "確認する", "Review & confirm"),
    ("删除这笔账", "取引を削除", "Delete this entry"),
    ("删除账目：", "取引を削除：", "Delete entry: "),
    ("账户余额与相关额度恢复点会重新计算；操作前保留完整备份。", "残高と関連する利用枠を再計算します。先に完全バックアップします。", "Balances and related credit recovery points will be recalculated after a full backup."),
    ("确认实际账户", "実際の口座を確認", "Confirm actual account"),
    ("核对余额", "残高照合", "Reconcile"),
)

# GitHub sign-in and legacy account migration.
_ROWS += (
    ("一个 GitHub 账号，就能开始", "GitHubアカウントですぐに開始", "Your GitHub account. Your ledger."),
    ("首次授权自动建立你的私人账本，以后在其他设备使用同一个 GitHub 登录即可。", "初回認証で専用の台帳を作成。同じGitHubアカウントで別の端末からもログインできます。", "First authorization creates your private ledger. Use the same GitHub account on your other devices."),
    ("使用 GitHub 登录", "GitHubでログイン", "Continue with GitHub"),
    ("密码只在 GitHub 页面输入；登录不会上传或覆盖云备份。", "パスワードはGitHubでのみ入力。ログインだけでクラウドを上書きしません。", "Enter your password only on GitHub. Signing in never uploads or replaces a cloud backup."),
    ("复制临时授权码，在 GitHub 验证页输入并确认，再返回这里。", "一時コードをコピーしてGitHubの認証画面で入力し、承認後に戻ってください。", "Copy this temporary code, enter it on GitHub and approve, then return here."),
    ("复制授权码", "コードをコピー", "Copy code"),
    ("打开 GitHub 授权", "GitHubの認証を開く", "Open GitHub authorization"),
    ("取消登录", "ログインを中止", "Cancel sign-in"),
    ("已有旧账号？迁移原账本", "以前のアカウントから台帳を移行", "Have an old account? Keep your ledger"),
    ("先验证原账号，再关联 GitHub，保留原来的账目和设置。新用户直接使用上方 GitHub 登录。", "旧アカウントを確認してからGitHubを連携し、既存データを保持します。新規の方は上のGitHubログインを使用してください。", "Verify your old account, then link GitHub to retain entries and settings. New users can sign in with GitHub above."),
    ("原账号密码", "旧パスワード", "Old password"),
    ("原账号恢复码", "旧復旧コード", "Old recovery code"),
    ("验证原账号并保留账本", "旧アカウントを確認して台帳を保持", "Verify old account and keep ledger"),
    ("关联 GitHub 后，以后直接使用 GitHub 登录，当前账本和设置会保留。", "GitHubを連携すると今後GitHubでログインできます。現在の台帳と設定は保持します。", "Link GitHub to sign in with it from now on, keeping this ledger and its settings."),
    ("关联 GitHub，保留当前账本", "GitHubを連携して現在の台帳を保持", "Link GitHub and keep this ledger"),
    ("正在连接 GitHub…", "GitHubに接続中…", "Connecting to GitHub…"),
    ("等待 GitHub 授权，完成后会自动进入账本。", "GitHubの承認を待っています。完了後、台帳を開きます。", "Waiting for GitHub authorization. Your ledger will open automatically."),
    ("连接暂时中断，返回页面后会继续检查。", "接続が中断されました。画面に戻ると再確認します。", "Connection interrupted. Return to this page to resume."),
    ("GitHub 登录成功", "GitHubでログインしました", "Signed in with GitHub"),
    ("GitHub 登录未完成，请重新发起并在 GitHub 确认授权。", "GitHubログインが完了しませんでした。再度開始してGitHubで承認してください。", "GitHub sign-in did not complete. Start again and approve on GitHub."),
    ("GitHub 登录已过期，请重新开始。", "GitHubログインの有効期限が切れました。再度開始してください。", "GitHub sign-in expired. Please start again."),
    ("GitHub 登录请求过多，请稍后再试。", "GitHubログインのリクエストが多すぎます。しばらくして再試行してください。", "Too many GitHub sign-in requests. Please try again later."),
    ("GitHub 授权地址校验失败，请稍后再试。", "GitHub認証先を確認できません。後で再試行してください。", "The GitHub verification address could not be validated. Try again later."),
    ("请先在 GitHub 完成授权。", "先にGitHubで認証を完了してください。", "Complete authorization on GitHub first."),
    ("原账号会话已变化，请重新验证原账号后关联。", "旧アカウントのセッションが変わりました。再確認してから連携してください。", "The old-account session changed. Verify it again before linking."),
    ("这个 GitHub 已关联另一份账本。当前账本保持不变，请使用原关联账号。", "このGitHubは別の台帳に連携済みです。現在のデータは保持されます。元の連携アカウントを使用してください。", "This GitHub account is linked to another ledger. This ledger is unchanged; use its original linked account."),
    ("当前账本已关联其他 GitHub，不能直接替换。", "この台帳は別のGitHubに連携済みで、直接変更できません。", "This ledger is already linked to another GitHub account and cannot be reassigned here."),
    ("原账号不存在，请重新登录。", "旧アカウントが見つかりません。再度ログインしてください。", "The old account was not found. Please sign in again."),
    ("找不到账号账本，请检查服务备份。", "台帳が見つかりません。サービスのバックアップを確認してください。", "The account ledger is missing. Check the service backups."),
    ("已改为使用 GitHub 登录，无需注册。", "GitHubログインに変更されました。新規登録は不要です。", "Use GitHub sign-in. No app registration is needed."),
)

_ROWS += (
    ("登录账号已变化，请刷新页面后再操作，待同步记录仍然保留。", "ログインアカウントが変わりました。画面を更新してください。未同期記録は保持されています。", "The signed-in account changed. Refresh before continuing; pending entries are retained."),
    ("待同步记录属于另一个账号，已停止写入。", "未同期記録は別アカウントのため、書き込みを停止しました。", "These pending entries belong to another account, so posting was stopped."),
)

_CATALOGS = {
    "ja-JP": {source: japanese for source, japanese, _english in _ROWS},
    "en-US": {source: english for source, _japanese, english in _ROWS},
}

_DYNAMIC_PATTERNS: tuple[tuple[re.Pattern[str], dict[str, str]], ...] = (
    (re.compile(r"^(.+)本期填写的还款金额超过扣款账户余额，未记账；请核对。$"), {
        "ja-JP": r"\1の今期返済額が引落口座の残高を超えています。記帳しませんでした。確認してください。",
        "en-US": r"The current repayment for \1 exceeds the payment account balance. It was not posted; please review.",
    }),
    (re.compile(r"^信用卡每月应还日期 (.+) 已过，软件未自动补记；请核对实际扣款。$"), {
        "ja-JP": r"クレジットカードの毎月の返済日 \1 は過ぎています。自動記帳していません。実際の引落しを確認してください。",
        "en-US": r"The monthly credit card due date \1 has passed. Nothing was posted automatically; verify the actual payment.",
    }),
    (re.compile(r"^(.+)今天是还款日，但本期金额未填写，未记账。$"), {
        "ja-JP": r"今日は\1の返済日ですが、今期の金額が未入力のため記帳していません。",
        "en-US": r"Today is \1's due date, but no amount was entered for this period. Nothing was posted.",
    }),
    (re.compile(r"^(.+)今天已有部分还款记录，软件没有自动补差；请核对本期金额。$"), {
        "ja-JP": r"今日は\1の一部返済が記録済みです。不足額は自動記帳していません。今期の金額を確認してください。",
        "en-US": r"A partial repayment for \1 is already recorded today. The app did not post the difference automatically; review this period's amount.",
    }),
    (re.compile(r"^(.+)今天已有还款记录，本期计划没有重复记账。$"), {
        "ja-JP": r"今日は\1の返済が記録済みのため、今期の予定は重複して記帳していません。",
        "en-US": r"A repayment for \1 is already recorded today, so this period's plan was not posted again.",
    }),
    (re.compile(r"^(.+)的每月应还计划设置有误，未记账。$"), {
        "ja-JP": r"\1の毎月返済予定に問題があるため、記帳していません。",
        "en-US": r"The monthly repayment plan for \1 is invalid; nothing was posted.",
    }),
    (re.compile(r"^当前显示 (\d+) 条采购商品。(?:其中 (\d+) 条待识别。)?$"), {
        "ja-JP": r"購入商品 \1 件を表示しています。未分類：\2 件。",
        "en-US": r"Showing \1 purchased items. Unclassified: \2.",
    }),
    (re.compile(r"^已保存 (\d+) 条采购食材记录。$"), {
        "ja-JP": r"食材の購入記録を\1件保存しました。",
        "en-US": r"Saved \1 food purchase records.",
    }),
    (re.compile(r"^已保存 (\d+) 条食用记录。$"), {
        "ja-JP": r"食事記録を\1件保存しました。",
        "en-US": r"Saved \1 food log records.",
    }),
    (re.compile(r"^已导入 (\d+) 条商品行，系统已自动分类，无法识别的项目会留在“待识别”。$"), {
        "ja-JP": r"商品行を\1件取り込み、自動分類しました。判別できない項目は「未分類」のままです。",
        "en-US": r"Imported \1 item rows and classified them. Unclear items remain unclassified.",
    }),
    (re.compile(r"^自动识别结果：(.+)。$"), {
        "ja-JP": r"自動分類結果：\1。",
        "en-US": r"Automatic classification: \1.",
    }),
    (re.compile(r"^定期收支已在本地账本自动记入 (\d+) 笔。$"), {
        "ja-JP": r"定期収支をローカル台帳に\1件自動記帳しました。",
        "en-US": r"Posted \1 recurring transactions to the local ledger.",
    }),
    (re.compile(r"^定期收支已匹配 (\d+) 条现有账本流水，没有重复记账。$"), {
        "ja-JP": r"既存の台帳取引\1件と一致しました。重複記帳はありません。",
        "en-US": r"Matched \1 existing ledger transactions; no duplicate entries were posted.",
    }),
    (re.compile(r"^定期收支“(.+)”处理失败，未推进日期：(.+)$"), {
        "ja-JP": r"定期収支「\1」の処理に失敗し、次回日付は更新されませんでした：\2",
        "en-US": r"Could not process recurring item “\1”; its next date was not advanced: \2",
    }),
    (re.compile(r"^定期收支已(启用|暂停)。$"), {
        "ja-JP": r"定期収支を\1しました。",
        "en-US": r"Recurring item \1.",
    }),
    (re.compile(r"^语言已切换，将立即生效。$"), {
        "ja-JP": r"言語を変更しました。すぐに反映されます。",
        "en-US": r"Language changed and applied.",
    }),
    (re.compile(r"^记账 Agent · (.+) / (.+) · 本地 SQLite 账本$"), {
        "ja-JP": r"家計簿Agent · \1 / \2 · ローカルSQLite台帳",
        "en-US": r"Bookkeeping agent · \1 / \2 · Local SQLite ledger",
    }),
    (re.compile(r"^饮食健康 Agent · (.+) / (.+) · 只读本地记录$"), {
        "ja-JP": r"食事と健康Agent · \1 / \2 · ローカル記録の読み取り専用",
        "en-US": r"Food & Health agent · \1 / \2 · Read-only local records",
    }),
    (re.compile(r"^饮食健康 Skill：已加载 (.+)；发送时读取最新内容。$"), {
        "ja-JP": r"食事と健康Skill：\1を読み込み済み。送信時に最新内容を読み込みます。",
        "en-US": r"Food & Health Skill: loaded \1; latest content is read when sending.",
    }),
    (re.compile(r"^记账 Skill：已加载 (.+)；发送时读取最新内容。$"), {
        "ja-JP": r"記帳Skill：\1を読み込み済み。送信時に最新内容を読み込みます。",
        "en-US": r"Bookkeeping Skill: loaded \1; latest content is read when sending.",
    }),
    (re.compile(r"^定期收支计划检查失败：(.+)$"), {
        "ja-JP": r"定期収支の確認に失敗しました：\1",
        "en-US": r"Recurring transaction check failed: \1",
    }),
    (re.compile(r"^自动还款计划检查失败：(.+)$"), {
        "ja-JP": r"自動返済予定の確認に失敗しました：\1",
        "en-US": r"Automatic repayment check failed: \1",
    }),
    (re.compile(r"^当前 API 服务的接口地址或模型名未填写，请先完成设置。$"), {
        "ja-JP": r"現在のAPIサービスにURLまたはモデル名がありません。設定してください。",
        "en-US": r"The active API service is missing an endpoint or model name. Complete its settings first.",
    }),
    (re.compile(r"^找到 (\d+) 条记录：(.+) 至 (.+)$"), {
        "ja-JP": r"\2～\3の取引：\1件",
        "en-US": r"\1 transactions: \2 through \3",
    }),
    (re.compile(r"^(.+)（账户扣款 (.+)）$"), {
        "ja-JP": r"\1（口座引落額 \2）",
        "en-US": r"\1 (account debit \2)",
    }),
    (re.compile(r"^已入账 / 待核对$"), {
        "ja-JP": r"記帳済み / 要確認",
        "en-US": r"Posted / Review",
    }),
    (re.compile(r"^备查 / 待核对$"), {
        "ja-JP": r"参考記録 / 要確認",
        "en-US": r"Memo / Review",
    }),
    (re.compile(r"^(\d[\d,]*)点$"), {
        "ja-JP": r"\1ポイント",
        "en-US": r"\1 points",
    }),
)

_PREFIXES: tuple[tuple[str, dict[str, str]], ...] = (
    ("自动保存失败：", {"ja-JP": "自動保存に失敗しました：", "en-US": "Auto-save failed: "}),
    ("无法加载 Skill：", {"ja-JP": "Skillを読み込めません：", "en-US": "Cannot load Skill: "}),
    ("记账 Skill 无法读取：", {"ja-JP": "記帳Skillを読み込めません：", "en-US": "Could not read bookkeeping Skill: "}),
    ("饮食健康 Skill 无法读取：", {"ja-JP": "食事と健康Skillを読み込めません：", "en-US": "Could not read Food & Health Skill: "}),
    ("模型分配保存失败：", {"ja-JP": "モデル割り当ての保存に失敗しました：", "en-US": "Could not save model assignment: "}),
    ("无法打开账本文件夹：\n", {"ja-JP": "台帳フォルダーを開けません：\n", "en-US": "Cannot open ledger folder:\n"}),
    ("定期收支计划检查失败：", {"ja-JP": "定期収支の確認に失敗しました：", "en-US": "Recurring transaction check failed: "}),
    ("API 服务配置中没有有效的服务项。", {"ja-JP": "APIサービス設定に有効な項目がありません。", "en-US": "No valid API service profile is configured."}),
    ("账本备份已保存到：\n", {"ja-JP": "台帳のバックアップを保存しました：\n", "en-US": "Ledger backup saved to:\n"}),
)


def _settings_path() -> Path:
    return app_data_directory() / "language.json"


def load_language() -> str:
    path = _settings_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, TypeError, AttributeError):
        return DEFAULT_LANGUAGE
    return value if value in _CATALOGS or value == DEFAULT_LANGUAGE else DEFAULT_LANGUAGE


def save_language(language: str) -> None:
    if language not in _CATALOGS and language != DEFAULT_LANGUAGE:
        raise ValueError("Unsupported application language")
    path = _settings_path()
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps({"version": 1, "language": language}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


_language = DEFAULT_LANGUAGE
_installed = False
_roots: list[tk.Misc] = []
_string_vars: dict[str, tk.StringVar] = {}
_display_var_sources: dict[str, str] = {}
_combo_var_maps: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
_originals: dict[str, Any] = {}


def current_language() -> str:
    return _language


def set_language(language: str) -> None:
    global _language
    if language not in _CATALOGS and language != DEFAULT_LANGUAGE:
        raise ValueError("Unsupported application language")
    _language = language


def _center_toplevel(window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
    """Center a child window over its owner and keep it on the visible screen."""
    try:
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        if width <= 1:
            width = window.winfo_reqwidth()
        if height <= 1:
            height = window.winfo_reqheight()

        screen_left = window.winfo_vrootx()
        screen_top = window.winfo_vrooty()
        virtual_width = window.winfo_vrootwidth() or window.winfo_screenwidth()
        virtual_height = window.winfo_vrootheight() or window.winfo_screenheight()

        owner: tk.Misc | None = None
        try:
            owner = parent.winfo_toplevel() if parent is not None else window._root()
        except tk.TclError:
            owner = None

        if owner is not None and owner is not window and owner.winfo_viewable():
            owner.update_idletasks()
            x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
            y = owner.winfo_rooty() + (owner.winfo_height() - height) // 2
        else:
            x = screen_left + (virtual_width - width) // 2
            y = screen_top + (virtual_height - height) // 2

        right_edge = screen_left + virtual_width
        bottom_edge = screen_top + virtual_height
        if width <= virtual_width - 16:
            x = min(max(screen_left + 8, x), right_edge - width - 8)
        else:
            x = screen_left + (virtual_width - width) // 2
        if height <= virtual_height - 16:
            y = min(max(screen_top + 8, y), bottom_edge - height - 8)
        else:
            y = screen_top + (virtual_height - height) // 2

        window.geometry(f"+{x}+{y}")
    except (tk.TclError, AttributeError):
        return


def _translate_dynamic(source: str, language: str) -> str | None:
    month_field = re.fullmatch(r"(.+)请使用 YYYY-MM 格式", source)
    if month_field:
        field = month_field.group(1)
        translated_field = translate(field, language)
        return (
            f"{translated_field}は YYYY-MM 形式で入力してください"
            if language == "ja-JP"
            else f"Enter {translated_field} as YYYY-MM"
        )
    invalid_month = re.fullmatch(r"(.+)不是有效月份：(.+)", source)
    if invalid_month:
        field, value = invalid_month.groups()
        translated_field = translate(field, language)
        return (
            f"{translated_field}が有効な月ではありません：{value}"
            if language == "ja-JP"
            else f"{value} is not a valid {translated_field.lower()} month"
        )
    fixed_asset_error = re.fullmatch(r"(已报废|计划报废) (\d{4}-\d{2})", source)
    if fixed_asset_error:
        status, month = fixed_asset_error.groups()
        status_map = {
            "已报废": ("廃棄済み", "Disposed"),
            "计划报废": ("廃棄予定", "Planned disposal"),
        }
        return f"{status_map[status][0]} {month}" if language == "ja-JP" else f"{status_map[status][1]} {month}"
    match = re.fullmatch(r"积分余额 (.+)，按1点=1 JPY估值，单独展示且不计入资产。固定资产行前的方框可逐项切换是否计入资产合计，切换后报表会自动刷新；折旧只调整资产负债表账面价值，不改变利润表或购买流水。信用卡负债为总额度−可用额度的差额，不等于当月应还账单。负余额不计入资产。(?:另有(\d+)张信用卡缺少额度快照。)?银行存款仅统计银行账户。", source)
    if match:
        points, missing_cards = match.groups()
        if language == "ja-JP":
            text = f"ポイント残高 {points}（1ポイント=1 JPY評価）は別表示で資産に含めません。固定資産の行の前にあるチェックボックスで資産合計への計上を切り替えられ、レポートは自動更新されます。償却は貸借対照表だけに反映し、損益計算書や購入取引を変更しません。カード負債は利用枠−利用可能額の差で、当月請求額ではありません。マイナス残高は資産に含めません。"
            if missing_cards:
                text += f" 利用枠スナップショットがないカードが{missing_cards}枚あります。"
            return text + " 銀行預金は銀行口座のみを集計します。"
        text = f"Points balance {points} (valued at 1 JPY per point) is shown separately and excluded from assets. Use the checkbox before each fixed-asset row to include or exclude it from total assets; the report refreshes automatically. Depreciation changes the balance sheet only; it does not change the income statement or purchase transactions. Card liabilities are total limit minus available credit, not the current bill. Negative balances are excluded from assets."
        if missing_cards:
            text += f" {missing_cards} card(s) have no credit-limit snapshot."
        return text + " Bank deposits include bank accounts only."
    match = re.fullmatch(r"(\d+)/(\d+)个月 · (\d+)%", source)
    if match:
        elapsed, life, percent = match.groups()
        if language == "ja-JP":
            return f"{elapsed}/{life}か月 · {percent}%"
        return f"{elapsed}/{life} months · {percent}%"
    match = re.fullmatch(r"(\d+)个月", source)
    if match:
        return f"{match.group(1)}か月" if language == "ja-JP" else f"{match.group(1)} months"
    match = re.fullmatch(r"(\d+)% · (\d+)/(\d+)", source)
    if match:
        percent, elapsed, life = match.groups()
        return f"{percent}% · {elapsed}/{life}"
    match = re.fullmatch(
        r"每月折旧：(.+)　累计折旧：(.+)　剩余账面价值：(.+)　购入原值：(.+?)(?:　报废月份：(\d{4}-\d{2})；该月起不计入资产负债表。)?",
        source,
    )
    if match:
        monthly, depreciated, remaining, cost, disposal_month = match.groups()
        template = translate(
            "每月折旧：{monthly}　累计折旧：{depreciated}　剩余账面价值：{remaining}　购入原值：{cost}", language
        ).format(monthly=monthly, depreciated=depreciated, remaining=remaining, cost=cost)
        if disposal_month:
            template += "　" + translate(
                "报废月份：{month}；该月起不计入资产负债表。", language
            ).format(month=disposal_month)
        return template
    match = re.fullmatch(r"共登记 (\d+) 项；截至 (\d{4}-\d{2}) 的进度按月份计算。", source)
    if match:
        count, month = match.groups()
        if language == "ja-JP":
            return f"登録資産は{count}件です。{month}時点の進捗は月単位で計算します。"
        return f"{count} assets registered; progress is calculated by month through {month}."
    match = re.fullmatch(r"原值 (.+)；累计折旧 (.+)；已使用 (\d+)/(\d+) 个月", source)
    if match:
        cost, depreciated, elapsed, life = match.groups()
        template = translate(
            "原值 {cost}；累计折旧 {depreciated}；已使用 {elapsed}/{life} 个月", language
        )
        return template.format(cost=cost, depreciated=depreciated, elapsed=elapsed, life=life)
    route_heading = re.fullmatch(
        r"(记账 Agent|饮食健康 Agent) · 文字 (.+) / 识图 (.+) · (只读本地记录|本地 SQLite 账本)",
        source,
    )
    if route_heading:
        agent, text_model, vision_model, suffix = route_heading.groups()
        return (
            f"{translate(agent, language)} · {translate('文字', language)} {text_model} / "
            f"{translate('识图', language)} {vision_model} · {translate(suffix, language)}"
        )
    route_status = re.fullmatch(r"(.+) 纯文字：(.+) — (.+)；含图片：(.+) — (.+)。", source)
    if route_status:
        agent, text_name, text_model, image_name, image_model = route_status.groups()
        return (
            f"{translate(agent, language)} {translate('纯文字', language)}: {text_name} — {text_model}; "
            f"{translate('含图片', language)}: {image_name} — {image_model}"
        )
    account_label = re.fullmatch(r"(.+)（(现金|银行|钱包|券/预付|交通卡|积分)）", source)
    if account_label:
        name, kind = account_label.groups()
        separator = "（" if language == "ja-JP" else " ("
        closing = "）" if language == "ja-JP" else ")"
        return f"{name}{separator}{translate(kind, language)}{closing}"
    if source.endswith("   ›"):
        return translate(source[:-4], language) + "   ›"
    match = re.fullmatch(r"新服务 (\d+)", source)
    if match:
        return (f"新しいサービス {match.group(1)}" if language == "ja-JP" else f"New service {match.group(1)}")
    match = re.fullmatch(r"(记账 Agent|饮食健康 Agent) 当前使用：(.+) — (.+)", source)
    if match:
        agent, service, model = match.groups()
        service = translate(service, language)
        model = translate(model, language)
        if language == "ja-JP":
            return f"{translate(agent, language)}が使用中：{service} — {model}"
        return f"{translate(agent, language)} using: {service} — {model}"
    for system_service_name in ("Ollama 本机", "环境变量 API", "旧 NVIDIA 配置（请更新密钥）", "未命名服务"):
        prefix = system_service_name + " — "
        if source.startswith(prefix):
            service_name = translate(system_service_name, language)
            model_name = translate(source[len(prefix) :], language)
            return f"{service_name} — {model_name}"
    match = re.fullmatch(r"选择(记账 Agent|饮食健康 Agent) Skill 文件", source)
    if match:
        agent = translate(match.group(1), language)
        return (f"{agent}のSkillファイルを選択" if language == "ja-JP" else f"Select {agent} Skill file")
    match = re.fullmatch(r"当前 (记账 Agent|饮食健康 Agent) 未加载 Skill。", source)
    if match:
        agent = translate(match.group(1), language)
        return (f"現在、{agent}のSkillは読み込まれていません。" if language == "ja-JP" else f"No Skill is loaded for {agent}.")
    if source.startswith("当前显示 ") and source.endswith(" 条采购商品。"):
        count = source[len("当前显示 ") : -len(" 条采购商品。")]
        if language == "ja-JP":
            return f"購入商品を{count}件表示しています。"
        return f"Showing {count} purchased items."
    if source.startswith("支付场景规则：已设置 ") and source.endswith(" 项；记账时按用途和币种匹配。"):
        count = source[len("支付场景规则：已设置 ") : -len(" 项；记账时按用途和币种匹配。")]
        if language == "ja-JP":
            return f"支払ルール：{count}件設定済み。記帳時に用途と通貨で照合します。"
        return f"Payment rules: {count} configured; matched by purpose and currency."
    if source.startswith("已附加 ") and " 张：" in source:
        count, rest = source[len("已附加 ") :].split(" 张：", 1)
        return (f"画像を{count}枚添付：{rest}" if language == "ja-JP" else f"Attached {count} images: {rest}")
    if source.startswith("备份保存在："):
        path = source[len("备份保存在：") :]
        return (f"バックアップ保存先：{path}" if language == "ja-JP" else f"Backups are stored at: {path}")
    match = re.fullmatch(r"当前 (记账 Agent|饮食健康 Agent) Skill：(.+)", source)
    if match:
        agent, path = match.groups()
        label = translate(agent, language)
        return (f"{label}の現在のSkill：{path}" if language == "ja-JP" else f"Current {label} Skill: {path}")
    match = re.fullmatch(r"已加载 (.+)；仅在使用(记账 Agent|饮食健康 Agent)时发送。", source)
    if match:
        skill_name, agent = match.groups()
        label = translate(agent, language)
        return (f"{skill_name}を読み込み済み。{label}の使用時のみ送信します。" if language == "ja-JP" else f"Loaded {skill_name}; sent only when using the {label}.")
    match = re.fullmatch(r"当前 (.+) Skill：(.+)", source)
    if match:
        skill_name, path = match.groups()
        return (f"現在の{skill_name} Skill：{path}" if language == "ja-JP" else f"Current {skill_name} Skill: {path}")
    match = re.fullmatch(r"当前显示 (\d+) 条采购商品。(?:其中 (\d+) 条待识别。)?", source)
    if match:
        count, unclassified = match.groups()
        if language == "ja-JP":
            result = f"購入商品を{count}件表示しています。"
            return result + (f"未分類：{unclassified}件。" if unclassified else "")
        result = f"Showing {count} purchased items."
        return result + (f" Unclassified: {unclassified}." if unclassified else "")
    match = re.fullmatch(r"自动识别结果：(.+)。", source)
    if match:
        label = translate(match.group(1), language)
        return (f"自動分類結果：{label}。" if language == "ja-JP" else f"Automatic classification: {label}.")
    match = re.fullmatch(r"定期收支已(启用|暂停)。", source)
    if match:
        enabled = match.group(1) == "启用"
        if language == "ja-JP":
            return "定期収支を有効にしました。" if enabled else "定期収支を一時停止しました。"
        return "Recurring item enabled." if enabled else "Recurring item paused."
    match = re.fullmatch(r"金额单位：(JPY|CNY)。本期金额只用于当前显示的下次还款日，不会复制到下个月。", source)
    if match:
        currency = match.group(1)
        return (
            f"金額単位：{currency}。今期の金額は表示中の次回返済日のみに適用され、翌月には引き継がれません。"
            if language == "ja-JP"
            else f"Amount unit: {currency}. This period's amount applies only to the displayed due date and will not carry over to next month."
        )
    match = re.fullmatch(r"账单金额（(JPY|CNY)）", source)
    if match:
        return (f"請求額（{match.group(1)}）" if language == "ja-JP" else f"Bill amount ({match.group(1)})")
    match = re.fullmatch(r"账单和付款账户均为(JPY|CNY)，按原币记账。到期时只在本地账本记录，不会连接银行或实际扣款。", source)
    if match:
        currency = match.group(1)
        return (
            f"請求と支払口座はいずれも{currency}です。原通貨で記帳します。期日にはローカル台帳に記録するだけで、銀行への接続や実際の引落しは行いません。"
            if language == "ja-JP"
            else f"The bill and payment account are both {currency}; the original currency is recorded. On the due date, only the local ledger is updated. No bank connection or actual debit occurs."
        )
    match = re.fullmatch(r"账单按(JPY|CNY)记录；所选账户使用(JPY|CNY)。到期时按账单日期的日次参考汇率换算账户扣款金额并保存汇率。(.*)", source)
    if match:
        bill_currency, account_currency, suffix = match.groups()
        if language == "ja-JP":
            result = f"請求は{bill_currency}、選択した口座は{account_currency}です。期日に請求日基準の日次参考レートで引落額を換算し、レートを保存します。"
            if suffix.startswith("发卡行实际入账"):
                result += "カード会社の実際の計上額は為替レートや手数料により異なる場合があります。カード明細を確認してください。この機能はローカル台帳に記録するだけで、実際の引落しは行いません。"
            elif suffix.startswith("实际汇差"):
                result += "実際の為替差額や手数料は現金管理で調整できます。この機能は記帳のみで、実際の引落しは行いません。"
            return result
        result = f"The bill is in {bill_currency}; the selected account uses {account_currency}. The due amount is converted using the daily reference rate for the bill date, which is saved."
        if suffix.startswith("发卡行实际入账"):
            result += " The card issuer may post a different amount due to exchange rates or fees. Check the card statement. This only updates the local ledger; no actual debit is made."
        elif suffix.startswith("实际汇差"):
            result += " Adjust actual exchange differences or fees in Cash Management. This only records the entry; it does not make an actual debit."
        return result
    match = re.fullmatch(r"已保存“(.+)”的扣款账户和还款日；本期金额按本月填写，未填写就不会自动记账。", source)
    if match:
        name = match.group(1)
        return (
            f"「{name}」の引落口座と返済日を保存しました。今期の金額は毎月入力してください。未入力の場合、自動記帳しません。"
            if language == "ja-JP"
            else f"Saved the payment account and due date for “{name}”. Enter the amount each month; it will not be posted automatically if left blank."
        )
    match = re.fullmatch(r"“(.+)”每月应还计划已(恢复|暂停)。", source)
    if match:
        name, state = match.groups()
        if language == "ja-JP":
            action = "再開" if state == "恢复" else "一時停止"
            return f"「{name}」の毎月返済予定を{action}しました。"
        action = "resumed" if state == "恢复" else "paused"
        return f"Monthly repayment plan for “{name}” was {action}."
    match = re.fullmatch(r"已按本期单独填写的金额在本地账本记入 #(\d+)：(.+) → (.+)，(.+)。这只是账本记录，不代表软件从银行实际扣款。", source)
    if match:
        transaction_id, source_account, card_name, amount = match.groups()
        return (
            f"当期に入力された金額で、返済 #{transaction_id}（{source_account} → {card_name}、{amount}）をローカル台帳に記録しました。これは台帳記録のみで、銀行からの実際の引落しではありません。"
            if language == "ja-JP"
            else f"Posted repayment #{transaction_id} ({source_account} → {card_name}, {amount}) using the amount entered for this period. This is a ledger entry only; the app did not debit the bank."
        )
    deleted_account = re.fullmatch(
        r"账户“(.+)”已删除。删除前备份：(.+?)( 默认首次盘点行已一并移除；需要时可用同名钱包账户重新添加。)?",
        source,
    )
    if deleted_account:
        account_name, backup_path, removed_default = deleted_account.groups()
        if language == "ja-JP":
            result = f"口座「{account_name}」を削除しました。削除前のバックアップ：{backup_path}。"
        else:
            result = f"Deleted account “{account_name}”. Pre-deletion backup: {backup_path}."
        if removed_default:
            result += " " + translate(removed_default.strip(), language)
        return result
    patterns = (
        (
            re.compile(r"^(.+)首次盘点：期初余额 (.+)。$"),
            {"ja-JP": r"\1の初回棚卸し：開始残高 \2。", "en-US": r"\1 initial count: opening balance \2."},
        ),
        (
            re.compile(r"^还款 #([0-9]+) 已记为 (.+) → (.+) 转账；可用额度已按记录更新，未另记消费。若还没有额度快照，仍需先录入快照。$"),
            {"ja-JP": r"返済 #\1 を\2 → \3の振替として記録しました。利用可能額を更新し、支出は追加していません。利用枠スナップショットがない場合は先に入力してください。", "en-US": r"Recorded repayment #\1 as a transfer from \2 to \3. Available credit was updated; no expense was added. Enter a credit limit snapshot if none exists."},
        ),
        (
            re.compile(r"^定期收支规则 #([0-9]+) 已保存。到期时自动写入本地账本。$"),
            {"ja-JP": r"定期収支ルール #\1 を保存しました。期日にローカル台帳へ自動記帳します。", "en-US": r"Saved recurring rule #\1. It will be posted to the local ledger when due."},
        ),
        (
            re.compile(r"^(.+)余额已校准为(.+)；差额已保存为余额快照，未生成账本分录。$"),
            {"ja-JP": r"\1の残高を\2に調整しました。差額は残高スナップショットに保存され、仕訳は作成されていません。", "en-US": r"\1 balance was adjusted to \2. The difference was saved as a balance snapshot; no ledger entry was created."},
        ),
        (
            re.compile(r"^(.+) #([0-9]+)：(.+) ([+−-])(.+)；新余额 (.+)。$"),
            {"ja-JP": r"\1 #\2：\3 \4\5；新しい残高 \6。", "en-US": r"\1 #\2: \3 \4\5; new balance \6."},
        ),
        (
            re.compile(r"^定期收支规则 #([0-9]+) 已保存。到期时自动写入本地账本。$"),
            {"ja-JP": r"定期収支ルール #\1 を保存しました。期日にローカル台帳へ自動記帳します。", "en-US": r"Saved recurring rule #\1. It will be posted to the local ledger when due."},
        ),
        (
            re.compile(r"^信用卡“(.+)”已登记；额度仍需单独录入快照。$"),
            {"ja-JP": r"クレジットカード「\1」を登録しました。利用枠は別途スナップショットを入力してください。", "en-US": r"Registered credit card “\1”. Enter a separate credit limit snapshot."},
        ),
        (
            re.compile(r"^“(.+)”的额度快照已保存；消费、退款和还款会调整可用额度，并更新当前欠款估算。$"),
            {"ja-JP": r"「\1」の利用枠スナップショットを保存しました。利用・返金・返済に応じて利用可能額と債務目安を更新します。", "en-US": r"Saved the credit limit snapshot for “\1”. Purchases, refunds, and repayments update available credit and the estimated debt."},
        ),
        (
            re.compile(r"^“(.+)”每月应还计划已(恢复|暂停)。$"),
            {"ja-JP": r"「\1」の毎月返済予定を\2しました。", "en-US": r"Monthly repayment plan for “\1” was \2."},
        ),
        (
            re.compile(r"^已附加(\d+)张图片；当前未安装 Pillow，图片将按原样发送。$"),
            {"ja-JP": r"画像を\1枚添付しました。Pillowが未インストールのため、画像は元のまま送信されます。", "en-US": r"Attached \1 image(s). Pillow is not installed, so the images will be sent unchanged."},
        ),
        (
            re.compile(r"^已附加(\d+)张图片；方向已校正并保留文字细节，原图不变。$"),
            {"ja-JP": r"画像を\1枚添付しました。向きを補正し、文字の細部を保っています。元画像は変更されません。", "en-US": r"Attached \1 image(s). Orientation was corrected and text detail preserved; the original images are unchanged."},
        ),
        (
            re.compile(r"^已附加 (\d+) 张：$"),
            {"ja-JP": r"添付画像（\1枚）：", "en-US": r"Attached images (\1):"},
        ),
        (
            re.compile(r"^“(.+)”的每月应还计划设置有误，未记账。$"),
            {"ja-JP": r"「\1」の毎月返済予定に問題があるため、記帳していません。", "en-US": r"The monthly repayment plan for “\1” is invalid; nothing was posted."},
        ),
        (
            re.compile(r"^API 服务“(.+)”已保存。$"),
            {"ja-JP": r"APIサービス「\1」を保存しました。", "en-US": r"Saved API service “\1”."},
        ),
        (
            re.compile(r"^已自动保存服务“(.+)”（(.+)）。$"),
            {"ja-JP": r"サービス「\1」を自動保存しました（\2）。", "en-US": r"Automatically saved service “\1” (\2)."},
        ),
        (
            re.compile(r"^当前正在编辑 API 服务“(.+)”；各 Agent 的实际服务在“Agent 配置与 Skill”页单独选择。$"),
            {"ja-JP": r"現在、APIサービス「\1」を編集中です。各Agentが使うサービスは「AgentとSkillの設定」で選択します。", "en-US": r"Editing API service “\1”. Choose each agent's active service on the Agent and Skill settings page."},
        ),
        (
            re.compile(r"^模型分配保存失败：(.+)$"),
            {"ja-JP": r"モデルの割り当てを保存できませんでした：\1", "en-US": r"Could not save the model assignment: \1"},
        ),
        (
            re.compile(r"^已加载：(.+)（(\d+) 字符）$"),
            {"ja-JP": r"読み込み済み：\1（\2文字）", "en-US": r"Loaded: \1 (\2 characters)"},
        ),
        (
            re.compile(r"^记账 Agent Skill 已更新；下次请求会读取最新内容。$"),
            {"ja-JP": "家計簿AgentのSkillを更新しました。次回のリクエストで最新内容を読み込みます。", "en-US": "Bookkeeping agent Skill updated; the latest content will be read on the next request."},
        ),
        (
            re.compile(r"^饮食健康 Agent Skill 已更新；下次请求会读取最新内容。$"),
            {"ja-JP": "食事と健康AgentのSkillを更新しました。次回のリクエストで最新内容を読み込みます。", "en-US": "Food & Health agent Skill updated; the latest content will be read on the next request."},
        ),
        (
            re.compile(r"^记账 Agent Skill 已卸载。$"),
            {"ja-JP": "家計簿AgentのSkillを解除しました。", "en-US": "Bookkeeping agent Skill unloaded."},
        ),
        (
            re.compile(r"^饮食健康 Agent Skill 已卸载。$"),
            {"ja-JP": "食事と健康AgentのSkillを解除しました。", "en-US": "Food & Health agent Skill unloaded."},
        ),
        (
            re.compile(r"^切换失败，保存当前服务配置时出错：(.+)$"),
            {"ja-JP": r"切り替えに失敗しました。現在のサービス設定を保存できません：\1", "en-US": r"Could not switch services because the current settings could not be saved: \1"},
        ),
        (
            re.compile(r"^创建失败，无法保存服务配置：(.+)$"),
            {"ja-JP": r"作成に失敗しました。サービス設定を保存できません：\1", "en-US": r"Could not create the service because its settings could not be saved: \1"},
        ),
        (
            re.compile(r"^删除失败，无法保存服务配置：(.+)$"),
            {"ja-JP": r"削除に失敗しました。サービス設定を保存できません：\1", "en-US": r"Could not delete the service because its settings could not be saved: \1"},
        ),
        (
            re.compile(r"^账户“(.+)”已添加，并按当前排序规则排列。没有创建额外收支分录。$"),
            {
                "ja-JP": r"口座「\1」を追加し、現在の並び順で表示しました。収入や支出は追加していません。",
                "en-US": r"Added account “\1” and sorted it using the current order. No income or expense entry was created.",
            },
        ),
        (
            re.compile(r"^当前 (.+) Skill：(.+)$"),
            {
                "ja-JP": r"現在の\1 Skill：\2",
                "en-US": r"Current \1 Skill: \2",
            },
        ),
        (
            re.compile(r"^已加载 (.+)；仅在使用(.+)时发送。$"),
            {
                "ja-JP": r"\1を読み込み済み。\2の使用時のみ送信します。",
                "en-US": r"Loaded \1; sent only when using \2.",
            },
        ),
        (
            re.compile(r"^截至 (.+?)　银行存款：(.+?)　全部货币资产：(.+?)　信用卡欠款估算：(.+?)　已确认账面负债：(.+)$"),
            {
                "ja-JP": r"基準日 \1　銀行預金：\2　全貨幣資産：\3　カード債務の目安：\4　確認済み台帳負債：\5",
                "en-US": r"As of \1　Bank deposits: \2　All monetary assets: \3　Estimated card debt: \4　Confirmed ledger liabilities: \5",
            },
        ),
        (
            re.compile(r"^本期：(.+) 至 (.+)$"),
            {"ja-JP": r"当期：\1 ～ \2", "en-US": r"Period: \1 to \2"},
        ),
        (
            re.compile(r"^统计截至 (.+)；当前银行存款：(.+)。消费合计包含备查支出；备查不改变账户余额。转账和信用卡还款不计作支出。$"),
            {
                "ja-JP": r"\1まで集計。現在の銀行預金：\2。支出合計には参考記録を含みますが、残高には影響しません。振替とカード返済は支出に含みません。",
                "en-US": r"Through \1; current bank deposits: \2. Expense totals include memo-only items, which do not affect balances. Transfers and card repayments are not expenses.",
            },
        ),
        (
            re.compile(r"^积分余额 (.+)，按1点=1 JPY估值，单独展示且不计入资产。信用卡负债为总额度−可用额度的差额，不等于当月应还账单。负余额不计入资产。(?:另有(\d+)张信用卡缺少额度快照。)?银行存款仅统计银行账户。$"),
            {
                "ja-JP": r"ポイント残高：\1（1ポイント=1 JPYとして評価）。別表示で資産には含めません。カード負債は利用限度額−利用可能額の差額で、当月請求額ではありません。マイナス残高は資産に含めません。\2銀行預金は銀行口座のみを集計します。",
                "en-US": r"Points balance: \1 (valued at 1 JPY per point), shown separately and excluded from assets. Card liabilities are total limit minus available credit, not the monthly bill. Negative balances are excluded from assets. \2Bank deposits include bank accounts only.",
            },
        ),
        (
            re.compile(r"^语言已切换，将立即生效。$"),
            {"ja-JP": r"表示言語を変更しました。すぐに反映されます。", "en-US": r"Language changed and applied."},
        ),
    )
    for pattern, translations in patterns:
        match = pattern.fullmatch(source)
        if match:
            result = match.expand(translations[language])
            return result.replace(" None", " ").replace("None銀行", "銀行").replace("NoneBank", "Bank")
    for pattern, translations in _DYNAMIC_PATTERNS:
        match = pattern.fullmatch(source)
        if match:
            return match.expand(translations[language])
    for prefix, translations in _PREFIXES:
        if source.startswith(prefix):
            return translations[language] + source[len(prefix) :]
    return None


def translate(value: Any, language: str | None = None) -> Any:
    if not isinstance(value, str):
        return value
    selected = language or _language
    if selected == DEFAULT_LANGUAGE:
        return value
    result = _CATALOGS.get(selected, {}).get(value)
    if result is not None:
        return result
    result = _translate_dynamic(value, selected)
    if result is not None:
        return result
    if "\n" in value or "\r" in value:
        pieces = re.split(r"(\r\n|\n|\r)", value)
        return "".join(
            piece if piece in {"\n", "\r", "\r\n"} else str(translate(piece, selected))
            for piece in pieces
        )
    return value


def _as_options(cnf: Any, kw: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    copied_cnf = dict(cnf) if isinstance(cnf, dict) else cnf
    copied_kw = dict(kw)
    return copied_cnf, copied_kw


def _get_option(cnf: Any, kw: dict[str, Any], name: str) -> Any:
    if name in kw:
        return kw[name]
    if isinstance(cnf, dict):
        return cnf.get(name)
    return None


def _set_option(cnf: Any, kw: dict[str, Any], name: str, value: Any) -> tuple[Any, dict[str, Any]]:
    if name in kw:
        kw[name] = value
    elif isinstance(cnf, dict) and name in cnf:
        cnf[name] = value
    else:
        kw[name] = value
    return cnf, kw


def _var_name(value: Any) -> str | None:
    if isinstance(value, tk.Variable):
        return str(value._name)
    if isinstance(value, str) and value:
        return value
    return None


def _register_combo_values(widget: ttk.Combobox, canonical: tuple[str, ...]) -> None:
    forward = {value: translate(value) for value in canonical}
    reverse = {display: value for value, display in forward.items()}
    widget._bk_i18n_values = canonical
    widget._bk_i18n_forward = forward
    widget._bk_i18n_reverse = reverse
    variable_name = getattr(widget, "_bk_i18n_var_name", None)
    if variable_name:
        _combo_var_maps[variable_name] = (forward, reverse)
        variable = _string_vars.get(variable_name)
        if variable is not None:
            raw = _originals["stringvar_get"](variable)
            canonical_value = reverse.get(raw, raw)
            if canonical_value in forward:
                _originals["stringvar_set"](variable, forward[canonical_value])


def _patch_tkinter() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    _originals["base_widget_init"] = tk.BaseWidget.__init__
    _originals["misc_configure"] = tk.Misc.configure
    _originals["wm_title"] = tk.Wm.wm_title
    _originals["stringvar_init"] = tk.StringVar.__init__
    _originals["stringvar_set"] = tk.StringVar.set
    _originals["stringvar_get"] = tk.StringVar.get
    _originals["combobox_get"] = ttk.Combobox.get
    _originals["tree_heading"] = ttk.Treeview.heading
    _originals["tree_item"] = ttk.Treeview.item
    _originals["notebook_add"] = ttk.Notebook.add
    _originals["notebook_tab"] = ttk.Notebook.tab
    _originals["toplevel_init"] = tk.Toplevel.__init__

    def centered_toplevel_init(self: tk.Toplevel, *args: Any, **kwargs: Any) -> None:
        parent = args[0] if args else kwargs.get("master")
        _originals["toplevel_init"](self, *args, **kwargs)
        try:
            self.after_idle(lambda: _center_toplevel(self, parent))
        except tk.TclError:
            pass

    tk.Toplevel.__init__ = centered_toplevel_init  # type: ignore[method-assign]

    def localized_widget_init(
        self: tk.BaseWidget,
        master: tk.Misc,
        widget_name: str,
        cnf: Any = None,
        kw: Any = None,
        extra: Any = (),
    ) -> None:
        original_cnf, original_kw = _as_options(cnf, dict(kw or {}))
        options = {}
        if isinstance(original_cnf, dict):
            options.update(original_cnf)
        if isinstance(original_kw, dict):
            options.update(original_kw)
        text = options.get("text")
        if isinstance(text, str):
            self._bk_i18n_source_text = text
            original_cnf, original_kw = _set_option(original_cnf, original_kw, "text", translate(text))
        raw_values = options.get("values")
        canonical_values: tuple[str, ...] | None = None
        if "combobox" in str(widget_name).lower() and isinstance(raw_values, (list, tuple)):
            canonical_values = tuple(str(item) for item in raw_values)
            display_values = tuple(translate(item) for item in canonical_values)
            original_cnf, original_kw = _set_option(original_cnf, original_kw, "values", display_values)
        _originals["base_widget_init"](self, master, widget_name, original_cnf or {}, original_kw or {}, extra)
        if canonical_values is not None and isinstance(self, ttk.Combobox):
            variable_name = _var_name(options.get("textvariable"))
            self._bk_i18n_var_name = variable_name
            _register_combo_values(self, canonical_values)
        widget_class = str(self.winfo_class()).lower()
        textvariable = options.get("textvariable")
        if textvariable is not None and any(
            widget_class.endswith(name)
            for name in ("label", "button", "checkbutton", "radiobutton", "labelframe", "message")
        ):
            variable_name = _var_name(textvariable)
            if variable_name:
                variable = _string_vars.get(variable_name)
                if variable is not None:
                    _display_var_sources[variable_name] = str(_originals["stringvar_get"](variable))
                    _originals["stringvar_set"](
                        variable,
                        translate(_display_var_sources[variable_name]),
                    )

    tk.BaseWidget.__init__ = localized_widget_init  # type: ignore[method-assign]

    def localized_configure(self: tk.Misc, cnf: Any = None, **kw: Any) -> Any:
        copied_cnf, copied_kw = _as_options(cnf, kw)
        text = _get_option(copied_cnf, copied_kw, "text")
        if isinstance(text, str):
            self._bk_i18n_source_text = text
            copied_cnf, copied_kw = _set_option(copied_cnf, copied_kw, "text", translate(text))
        if isinstance(self, ttk.Combobox):
            variable = _get_option(copied_cnf, copied_kw, "textvariable")
            variable_name = _var_name(variable) if variable is not None else getattr(self, "_bk_i18n_var_name", None)
            raw_values = _get_option(copied_cnf, copied_kw, "values")
            if raw_values is not None:
                canonical = tuple(str(item) for item in raw_values)
                display = tuple(translate(item) for item in canonical)
                self._bk_i18n_var_name = variable_name
                _register_combo_values(self, canonical)
                copied_cnf, copied_kw = _set_option(copied_cnf, copied_kw, "values", display)
        return _originals["misc_configure"](self, copied_cnf, **copied_kw)

    tk.Misc.configure = localized_configure  # type: ignore[method-assign]
    tk.Misc.config = localized_configure  # type: ignore[method-assign]

    def localized_title(self: tk.Wm, string: Any = None) -> Any:
        if string is None:
            return _originals["wm_title"](self)
        if isinstance(string, str):
            self._bk_i18n_source_title = string
            string = translate(string)
        return _originals["wm_title"](self, string)

    tk.Wm.wm_title = localized_title  # type: ignore[method-assign]
    tk.Wm.title = localized_title  # type: ignore[method-assign]

    def localized_stringvar_init(self: tk.StringVar, *args: Any, **kwargs: Any) -> None:
        _originals["stringvar_init"](self, *args, **kwargs)
        _string_vars[str(self._name)] = self

    def localized_stringvar_set(self: tk.StringVar, value: Any) -> None:
        name = str(self._name)
        source = str(value)
        if name in _combo_var_maps:
            forward, _reverse = _combo_var_maps[name]
            _originals["stringvar_set"](self, forward.get(source, source))
            return
        if name in _display_var_sources:
            _display_var_sources[name] = source
            _originals["stringvar_set"](self, translate(source))
            return
        _originals["stringvar_set"](self, value)

    def localized_stringvar_get(self: tk.StringVar) -> Any:
        value = _originals["stringvar_get"](self)
        maps = _combo_var_maps.get(str(self._name))
        if maps:
            return maps[1].get(value, value)
        return value

    tk.StringVar.__init__ = localized_stringvar_init  # type: ignore[method-assign]
    tk.StringVar.set = localized_stringvar_set  # type: ignore[method-assign]
    tk.StringVar.get = localized_stringvar_get  # type: ignore[method-assign]

    def localized_combo_get(self: ttk.Combobox) -> str:
        value = _originals["combobox_get"](self)
        return getattr(self, "_bk_i18n_reverse", {}).get(value, value)

    ttk.Combobox.get = localized_combo_get  # type: ignore[method-assign]

    def localized_tree_heading(self: ttk.Treeview, column: str, option: Any = None, **kw: Any) -> Any:
        if getattr(self, "_bk_i18n_manual_headings", False):
            return _originals["tree_heading"](self, column, option, **kw)
        if isinstance(option, dict):
            options = dict(option)
            text = options.get("text")
            if isinstance(text, str):
                self._bk_i18n_headings = getattr(self, "_bk_i18n_headings", {})
                self._bk_i18n_headings[str(column)] = text
                options["text"] = translate(text)
            return _originals["tree_heading"](self, column, options, **kw)
        if isinstance(kw.get("text"), str):
            source = kw["text"]
            self._bk_i18n_headings = getattr(self, "_bk_i18n_headings", {})
            self._bk_i18n_headings[str(column)] = source
            kw["text"] = translate(source)
        return _originals["tree_heading"](self, column, option, **kw)

    ttk.Treeview.heading = localized_tree_heading  # type: ignore[method-assign]

    def localized_notebook_add(self: ttk.Notebook, child: Any, **kw: Any) -> Any:
        text = kw.get("text")
        if isinstance(text, str):
            tabs = getattr(self, "_bk_i18n_tabs", {})
            tabs[str(child)] = text
            self._bk_i18n_tabs = tabs
            kw["text"] = translate(text)
        return _originals["notebook_add"](self, child, **kw)

    ttk.Notebook.add = localized_notebook_add  # type: ignore[method-assign]

    def localized_notebook_tab(self: ttk.Notebook, tab_id: Any, option: Any = None, **kw: Any) -> Any:
        if isinstance(option, dict):
            options = dict(option)
            text = options.get("text")
            if isinstance(text, str):
                self._bk_i18n_tabs = getattr(self, "_bk_i18n_tabs", {})
                self._bk_i18n_tabs[str(tab_id)] = text
                options["text"] = translate(text)
            return _originals["notebook_tab"](self, tab_id, options, **kw)
        if isinstance(kw.get("text"), str):
            source = kw["text"]
            self._bk_i18n_tabs = getattr(self, "_bk_i18n_tabs", {})
            self._bk_i18n_tabs[str(tab_id)] = source
            kw["text"] = translate(source)
        return _originals["notebook_tab"](self, tab_id, option, **kw)

    ttk.Notebook.tab = localized_notebook_tab  # type: ignore[method-assign]

    for name in (
        "showinfo", "showwarning", "showerror", "askquestion", "askokcancel",
        "askyesno", "askyesnocancel", "askretrycancel",
    ):
        original = getattr(messagebox, name)
        _originals[f"messagebox_{name}"] = original

        def make_messagebox_wrapper(original_call: Any) -> Any:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                changed_args = list(args)
                if len(changed_args) > 0:
                    changed_args[0] = translate(changed_args[0])
                if len(changed_args) > 1:
                    changed_args[1] = translate(changed_args[1])
                if "title" in kwargs:
                    kwargs["title"] = translate(kwargs["title"])
                if "message" in kwargs:
                    kwargs["message"] = translate(kwargs["message"])
                return original_call(*changed_args, **kwargs)
            return wrapper

        setattr(messagebox, name, make_messagebox_wrapper(original))

    for name in ("askopenfilename", "askopenfilenames", "askdirectory", "asksaveasfilename"):
        original = getattr(filedialog, name)
        _originals[f"filedialog_{name}"] = original

        def make_filedialog_wrapper(original_call: Any) -> Any:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if "title" in kwargs:
                    kwargs["title"] = translate(kwargs["title"])
                if "filetypes" in kwargs:
                    kwargs["filetypes"] = tuple(
                        (translate(label), pattern)
                        for label, pattern in kwargs["filetypes"]
                    )
                return original_call(*args, **kwargs)
            return wrapper

        setattr(filedialog, name, make_filedialog_wrapper(original))


def _walk_widgets(widget: tk.Misc):
    yield widget
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return
    for child in children:
        yield from _walk_widgets(child)


def _native_configure(widget: tk.Misc, **kwargs: Any) -> None:
    # Bypass the localization wrapper so the original Chinese key remains on
    # each widget and a later language switch can translate it again.
    _originals["misc_configure"](widget, **kwargs)


def _refresh_combo(widget: ttk.Combobox) -> None:
    canonical = getattr(widget, "_bk_i18n_values", None)
    if canonical is None:
        return
    old_reverse = getattr(widget, "_bk_i18n_reverse", {})
    try:
        old_value = _originals["combobox_get"](widget)
    except tk.TclError:
        old_value = ""
    canonical_value = old_reverse.get(old_value, old_value)
    forward = {value: translate(value) for value in canonical}
    reverse = {display: value for value, display in forward.items()}
    widget._bk_i18n_forward = forward
    widget._bk_i18n_reverse = reverse
    variable_name = getattr(widget, "_bk_i18n_var_name", None)
    if variable_name:
        _combo_var_maps[variable_name] = (forward, reverse)
    _native_configure(widget, values=tuple(forward[value] for value in canonical))
    if canonical_value in forward:
        variable = _string_vars.get(variable_name or "")
        if variable is not None:
            _originals["stringvar_set"](variable, forward[canonical_value])
        else:
            try:
                widget.set(forward[canonical_value])
            except tk.TclError:
                pass


def apply_language(root: tk.Misc) -> None:
    if not _installed:
        return
    for widget in _walk_widgets(root):
        source_text = getattr(widget, "_bk_i18n_source_text", None)
        if isinstance(source_text, str):
            _native_configure(widget, text=translate(source_text))
        if isinstance(widget, ttk.Combobox):
            _refresh_combo(widget)
        headings = getattr(widget, "_bk_i18n_headings", {})
        if isinstance(widget, ttk.Treeview):
            for column, source in headings.items():
                _originals["tree_heading"](widget, column, text=translate(source))
            row_values = getattr(widget, "_bk_i18n_item_values", {})
            row_translatable = getattr(widget, "_bk_i18n_row_translatable", {})
            for item_id, source_values in row_values.items():
                try:
                    translated_values = tuple(
                        translate_tree_item(value) if index in row_translatable.get(item_id, set()) else value
                        for index, value in enumerate(source_values)
                    )
                    _originals["tree_item"](
                        widget, item_id, values=translated_values
                    )
                except tk.TclError:
                    continue
        tabs = getattr(widget, "_bk_i18n_tabs", {})
        if isinstance(widget, ttk.Notebook):
            for child, source in tabs.items():
                try:
                    _originals["notebook_tab"](widget, child, text=translate(source))
                except tk.TclError:
                    continue
        source_title = getattr(widget, "_bk_i18n_source_title", None)
        if isinstance(source_title, str):
            _originals["wm_title"](widget, translate(source_title))
    for name, source in tuple(_display_var_sources.items()):
        variable = _string_vars.get(name)
        if variable is not None:
            _originals["stringvar_set"](variable, translate(source))


def install_tk_localization(root: tk.Misc, language: str) -> None:
    global _language
    _patch_tkinter()
    _language = language if language in _CATALOGS or language == DEFAULT_LANGUAGE else DEFAULT_LANGUAGE
    if root not in _roots:
        _roots.append(root)


def translate_tree_item(item: Any) -> Any:
    """Translate fixed UI values in report rows while leaving user data intact."""
    if isinstance(item, tuple):
        return tuple(translate_tree_item(value) for value in item)
    if isinstance(item, list):
        return [translate_tree_item(value) for value in item]
    if not isinstance(item, str):
        return item
    result = translate(item)
    if result != item:
        return result
    stripped = item.strip()
    if stripped != item:
        translated = translate(stripped)
        if translated != stripped:
            return item[: len(item) - len(item.lstrip())] + str(translated)
    if item.startswith("支出分类："):
        prefix = translate("支出分类：")
        return prefix + item[len("支出分类：") :]
    if item.startswith("其中："):
        label, separator, detail = item.partition(" ")
        translated_label = translate(label)
        return translated_label + (separator + detail if separator else "")
    fixed_asset_row = re.fullmatch(r"(\s*)(.+?)（(原值 .+；累计折旧 .+；已使用 \d+/\d+ 个月)）", item)
    if fixed_asset_row:
        prefix, name, detail = fixed_asset_row.groups()
        return f"{prefix}{name}（{translate(detail)}）"
    match = re.fullmatch(r"(\s*)(JPY|CNY)(资产负债|资产合计|负债小计|负债合计|净资产（已计负债）|资产|负债)", item)
    if match:
        prefix, code, suffix = match.groups()
        suffix_map = {
            "ja-JP": {
                "资产负债": "の資産・負債", "资产合计": "資産合計", "负债小计": "負債小計",
                "负债合计": "負債合計", "净资产（已计负债）": "純資産（負債控除後）", "资产": "資産", "负债": "負債",
            },
            "en-US": {
                "资产负债": " assets & liabilities", "资产合计": " total assets", "负债小计": " liabilities subtotal",
                "负债合计": " total liabilities", "净资产（已计负债）": " net assets (after liabilities)", "资产": " assets", "负债": " liabilities",
            },
        }
        return prefix + code + suffix_map.get(_language, {}).get(suffix, suffix)
    match = re.fullmatch(r"(\s*)(.+?)（(包含推算期初|记录不完整|已确认|待核对)）", item)
    if match:
        prefix, name, status = match.groups()
        status_text = translate(status)
        return f"{prefix}{name} ({status_text})"
    return item
