/*
 * demo-crm/data/customers.js
 * ダミーの顧客データ（30件）+ localStorage 連携ヘルパー
 * ※ すべて架空の会社・人物・連絡先です。
 */
(function (global) {
  "use strict";

  var CUSTOMERS_SEED = [
    { company: "株式会社アオゾラ商事", person: "山田 太郎", phone: "03-1234-5601", email: "yamada@aozora-shoji.example.com", plan: "スタンダード", status: "契約済み", updated: "2026-08-01" },
    { company: "有限会社ふじの製作所", person: "鈴木 花子", phone: "045-222-5602", email: "suzuki@fujino-seisaku.example.com", plan: "フリー", status: "商談中", updated: "2026-08-02" },
    { company: "みなと物流株式会社", person: "佐藤 健一", phone: "078-333-5603", email: "sato@minato-logi.example.com", plan: "プレミアム", status: "契約済み", updated: "2026-08-03" },
    { company: "サクラ食品工業", person: "高橋 美咲", phone: "052-444-5604", email: "takahashi@sakura-food.example.com", plan: "スタンダード", status: "見込み客", updated: "2026-08-04" },
    { company: "北都建設株式会社", person: "田中 誠", phone: "011-555-5605", email: "tanaka@hokuto-kensetsu.example.com", plan: "プレミアム", status: "契約済み", updated: "2026-08-05" },
    { company: "green leaf カフェ", person: "伊藤 さくら", phone: "092-666-5606", email: "ito@greenleaf-cafe.example.com", plan: "フリー", status: "休眠", updated: "2026-07-20" },
    { company: "株式会社ヒカリ通信", person: "渡辺 大輔", phone: "022-777-5607", email: "watanabe@hikari-tsushin.example.com", plan: "スタンダード", status: "契約済み", updated: "2026-08-06" },
    { company: "つばさ運輸株式会社", person: "中村 由美", phone: "082-888-5608", email: "nakamura@tsubasa-unyu.example.com", plan: "フリー", status: "商談中", updated: "2026-08-06" },
    { company: "南風デザイン事務所", person: "小林 直樹", phone: "098-999-5609", email: "kobayashi@minamikaze-design.example.com", plan: "スタンダード", status: "見込み客", updated: "2026-08-07" },
    { company: "株式会社エムズ電機", person: "加藤 亮", phone: "06-1010-5610", email: "kato@ms-denki.example.com", plan: "プレミアム", status: "契約済み", updated: "2026-08-07" },
    { company: "はまなす農園", person: "吉田 恵", phone: "0138-11-5611", email: "yoshida@hamanasu-nouen.example.com", plan: "フリー", status: "休眠", updated: "2026-06-15" },
    { company: "株式会社リバーサイド不動産", person: "山本 隆", phone: "03-2020-5612", email: "yamamoto@riverside-fudousan.example.com", plan: "スタンダード", status: "契約済み", updated: "2026-08-08" },
    { company: "そよかぜ薬局", person: "松本 あゆみ", phone: "052-303-5613", email: "matsumoto@soyokaze-pharm.example.com", plan: "フリー", status: "商談中", updated: "2026-08-08" },
    { company: "有限会社タカラ印刷", person: "井上 学", phone: "075-404-5614", email: "inoue@takara-insatsu.example.com", plan: "スタンダード", status: "見込み客", updated: "2026-08-09" },
    { company: "株式会社オリオン精密", person: "木村 洋介", phone: "042-505-5615", email: "kimura@orion-seimitsu.example.com", plan: "プレミアム", status: "契約済み", updated: "2026-08-09" },
    { company: "こもれび保育園", person: "林 智子", phone: "029-606-5616", email: "hayashi@komorebi-hoiku.example.com", plan: "フリー", status: "契約済み", updated: "2026-08-10" },
    { company: "潮風水産株式会社", person: "斎藤 拓也", phone: "088-707-5617", email: "saito@shiokaze-suisan.example.com", plan: "スタンダード", status: "商談中", updated: "2026-08-10" },
    { company: "株式会社アップルロード", person: "清水 里奈", phone: "023-808-5618", email: "shimizu@appleroad.example.com", plan: "フリー", status: "見込み客", updated: "2026-08-11" },
    { company: "山手学習塾", person: "山口 大地", phone: "045-909-5619", email: "yamaguchi@yamate-juku.example.com", plan: "フリー", status: "休眠", updated: "2026-06-30" },
    { company: "株式会社コスモ倉庫", person: "森 めぐみ", phone: "072-010-5620", email: "mori@cosmo-wh.example.com", plan: "プレミアム", status: "契約済み", updated: "2026-08-11" },
    { company: "有限会社青葉クリーニング", person: "池田 隼人", phone: "086-111-5621", email: "ikeda@aoba-cleaning.example.com", plan: "フリー", status: "商談中", updated: "2026-08-12" },
    { company: "株式会社白鳥ホテルズ", person: "橋本 のぞみ", phone: "0776-22-5622", email: "hashimoto@hakucho-hotels.example.com", plan: "プレミアム", status: "契約済み", updated: "2026-08-12" },
    { company: "ふくろう書店", person: "山下 修", phone: "011-323-5623", email: "yamashita@fukurou-books.example.com", plan: "フリー", status: "見込み客", updated: "2026-08-13" },
    { company: "株式会社テラダ金属", person: "石川 剛", phone: "0532-44-5624", email: "ishikawa@terada-kinzoku.example.com", plan: "スタンダード", status: "契約済み", updated: "2026-08-13" },
    { company: "ひだまり訪問看護", person: "前田 沙織", phone: "092-525-5625", email: "maeda@hidamari-kango.example.com", plan: "スタンダード", status: "商談中", updated: "2026-08-14" },
    { company: "株式会社カエデ旅行社", person: "藤田 健太", phone: "03-6262-5626", email: "fujita@kaede-travel.example.com", plan: "フリー", status: "休眠", updated: "2026-07-01" },
    { company: "銀河エネルギー株式会社", person: "後藤 千尋", phone: "025-727-5627", email: "goto@ginga-energy.example.com", plan: "プレミアム", status: "契約済み", updated: "2026-08-14" },
    { company: "有限会社まつり菓子舗", person: "近藤 蓮", phone: "059-828-5628", email: "kondo@matsuri-kashiho.example.com", plan: "フリー", status: "見込み客", updated: "2026-08-15" },
    { company: "株式会社サンライズ警備", person: "村上 陽子", phone: "096-929-5629", email: "murakami@sunrise-keibi.example.com", plan: "スタンダード", status: "契約済み", updated: "2026-08-15" },
    { company: "みちのく製紙株式会社", person: "遠藤 康弘", phone: "0192-30-5630", email: "endo@michinoku-paper.example.com", plan: "スタンダード", status: "商談中", updated: "2026-08-16" }
  ];

  var STORAGE_KEY = "webautolab_demo_customers";

  function getExtraCustomers() {
    try {
      var raw = global.localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function addCustomer(customer) {
    var list = getExtraCustomers();
    list.push(customer);
    global.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    return list;
  }

  function getAllCustomers() {
    return CUSTOMERS_SEED.concat(getExtraCustomers());
  }

  global.DemoCRM = {
    CUSTOMERS_SEED: CUSTOMERS_SEED,
    STORAGE_KEY: STORAGE_KEY,
    getExtraCustomers: getExtraCustomers,
    addCustomer: addCustomer,
    getAllCustomers: getAllCustomers
  };
})(window);
