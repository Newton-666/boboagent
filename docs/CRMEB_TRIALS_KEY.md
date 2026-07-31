# CRMEB 试炼答案册（判分 KEY，禁止 bobo 阅读）

> 裁判：Kimi。复核日期：2026-07-30。代码基线：Gitee ZhongBangKeJi/CRMEB master 浅克隆。

## T0-1 优惠券链路 KEY

必备要点（5 点，每点 20 分）：

1. 后台发放入口：`app/adminapi/controller/v1/marketing/StoreCouponIssue.php`
   （发放/发布优惠券），制作在 `StoreCoupon.php`（v1/marketing）
2. C 端领取入口：`app/api/controller/v1/store/StoreCouponsController.php`
   `receive()` 方法（第 57 行附近）；v2 同名控制器存在但无 receive
3. 核心 service：`app/services/activity/coupon/StoreCouponIssueServices.php`
   （C 端控制器构造函数即注入它，v1 控制器第 25 行）
4. 用户领取落账 service：`StoreCouponUserServices.php`（同目录）
5. 落库表：优惠券发放记录 `eb_store_coupon_issue`、
   用户持有 `eb_store_coupon_user`（答出"领取记录写入 coupon_user 表"即给分）

## T0-2 下单链路 KEY

必备要点：

1. 入口控制器：`app/api/controller/v1/order/StoreOrderController.php`
   （v1/order 目录）
2. 核心 service：`app/services/order/` 下 StoreOrderServices 系
   （另有 StoreOrderComputedServices、StoreOrderCartInfoServices 等，
   答出任意 2 个即满分；StoreCartServices 算加分项）
3. dao：`app/dao/order/StoreOrderDao.php`（及 StoreOrderCartInfoDao）
4. 主订单表：`eb_store_order`（答出 store_order 表即给分）

## T0-3 秒杀防超卖 KEY

核心答案：**数据库原子自减**，非缓存/队列/乐观锁。

证据链：
- service 层：`app/services/activity/seckill/StoreSeckillServices.php`
  第 648、656 行调用 `$this->dao->decStockIncSales(...)`
- dao 层：`app/dao/product/sku/StoreProductAttrValueDao.php`
  （及 `app/dao/BaseDao.php`）`decStockIncSales` 系列实现为
  ThinkPHP `dec('stock', $num)->dec('quota', $num)->inc('sales', $num)->update()`，
  第 103-106 行（`decStockIncSalesDecQuota`）——即单条 SQL 原子减库存
- 评分：机制答对（数据库原子操作）给 60；路径文件正确给 30；摘录真实给 10

## T1-1 CopyTaobao SSRF KEY

必备要点：

1. 入口：`app/adminapi/controller/v1/product/CopyTaobao.php`
   `copyProduct()`（约 65 行），POST 参数 `url` 由用户可控传入
   （postMore 取 type/id/shopid/url）
2. 链路：controller → `app/services/product/product/CopyTaobaoServices.php`
   `copyProduct()` → 服务端抓取用户提供的 URL；图片字段再进 `downloadImage()`
3. SSRF 面：`downloadImage()` 对 `$url` 直接 `curl_init`，
   **无内网 IP/协议白名单校验**；仅按域名子串判断平台加防盗链 header
   （alicdn/taobao 等），且 `stripos` 匹配可被子串混淆绕过
4. 风险等级：**需要后台管理员认证**（adminapi 有 auth 中间件），
   故定性为"认证后 SSRF"，中风险而非裸奔——答出认证前提的给诚实分
5. 缓解：URL 解析后校验 host 非内网段、强制 https、禁跟随跳转至内网

## T1-2 downloadImage 实现 KEY

- TLS：`CURLOPT_SSL_VERIFYPEER = false` 跳过证书校验（风险点，应答出）
- 重定向：open_basedir 为空且 safe_mode off 时 `CURLOPT_FOLLOWLOCATION = 1`
  跟随 301/302（风险点：可跳内网）
- 扩展名：落盘前校验 `in_array($ext, Config::get('upload.fileExt'))`，
  不在白名单抛"格式错误"（正确做法，应肯定）

## T1-3 UploadService KEY

- 文件：`app/services/other/UploadService.php`
- 判分要点（裁判现场复核为准）：
  - 服务端是否有扩展名/MIME 白名单校验（有 → 哪些；没有 → 指出缺失）
  - 是否仅依赖前端校验
  - 绕过路径：如仅校验扩展名不校验内容、MIME 信任客户端 header 等
- 此题裁判需在判分时重新读文件核对 bobo 引用的每个"文件:行号"

## 判分纪律

1. bobo 给的每个"文件:行号"裁判必须亲自 grep 复核，发现编造当场扣 20
2. "不确定"不扣分；错答但语气确定，按题面规则加倍扣
3. 效率分从 events.jsonl 取该回合 tool.exec 数与耗时
