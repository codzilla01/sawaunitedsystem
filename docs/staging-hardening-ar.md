# تنفيذ staging وتأمين الحافة والخدمات الخارجية

> الإعداد البرمجي موجود، لكن لا يمكن إنشاء مشروع Vercel أو AWS أو نشر staging من المستودع وحده من دون حسابات وأسرار خاصة. أضيفت هذه الخطوات وWorkflow يدوي؛ لا تضع أي Token أو كلمة مرور في Git أو المحادثة.

## 1. بيئة staging منفصلة

أنشئ قاعدة PostgreSQL وbucket وماسحًا منفصلين تمامًا عن الإنتاج، واستخدم نطاق HTTPS ثابتًا مثل `staging.example.com`. اضبط **Preview Environment** في Vercel على:

- `APP_ENV=production`, `COOKIE_SECURE=true`, و`PUBLIC_ORIGIN` مطابقًا تمامًا لأصل نطاق staging الثابت، بلا مسار أو شرطة أخيرة.
- `SECRET_KEY` و`MFA_ENCRYPTION_KEY` عشوائيين ومختلفين عن الإنتاج. لإنشاء مفتاح Fernet:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `DATABASE_URL` لقاعدة staging مع TLS (`sslmode=require` أو أقوى)، لا قاعدة الإنتاج.
- `S3_BUCKET` و`S3_REGION` وبيانات IAM محدودة الصلاحية للـbucket الخاص ببيئة staging فقط.
- `DOCUMENT_SCANNER_URL` على HTTPS و`DOCUMENT_SCANNER_TOKEN` مطابق للماسح التجريبي.
- لا تضع كلمة مرور `BOOTSTRAP_ADMIN_PASSWORD` الدائمة في Vercel بعد إنشاء المدير الأولي.
- احفظ `MFA_ENCRYPTION_KEY` في مدير أسرار مؤسسي ونسخة استرداد محمية منفصلة؛ لا توجد آلية تدوير شفاف للمفتاح. فقدانه يمنع فك أسرار MFA ويستلزم إعادة تسجيل الحسابات إداريًا.

استخدم بيئة GitHub المسماة `staging`، وأضف إليها الأسرار التالية من إعدادات GitHub الآمنة: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`, `VERCEL_STAGING_DOMAIN` (اسم النطاق فقط)، `STAGING_BASE_URL` (مثل `https://staging.example.com`) و`ALERT_WEBHOOK_URL` (اختياري، HTTPS). يتطلب فحص الـworkflow والـmonitor أن يكون النطاق قد رُبط بالمشروع مسبقًا.

يمكن تشغيل `.github/workflows/staging-deploy.yml` يدويًا من GitHub. يسحب إعداد Preview، يبني Vercel، ينشر Preview، يربط النطاق الثابت، ثم يتحقق من `/health` و`/ready`. لا ينجح هذا الـworkflow قبل إنشاء المشروع وربط النطاق وإضافة الأسرار أعلاه وإعداد متغيرات Preview في Vercel.

## 2. إنشاء S3 خاص

القالب `infra/aws/private-documents-bucket.yml` ينشئ bucket مع:

- منع كامل للوصول العام وفرض ملكية bucket.
- Versioning وتشفير SSE-S3، مع `DeletionPolicy: Retain` و`UpdateReplacePolicy: Retain` لحماية الكائنات عند حذف/استبدال الـstack.
- رفض النقل غير المشفر ورفض الكتابة دون `AES256`.
- Managed Policy مقصورة على `GetObject`, `PutObject`, `DeleteObject` للكائنات داخل هذا bucket؛ لا تمنح التطبيق صلاحيات إدارة الحساب أو الـbucket.

أنشئ IAM user مخصصًا مسبقًا ثم طبّق القالب في حساب staging:

```bash
aws cloudformation deploy \
  --stack-name sawa-staging-documents \
  --template-file infra/aws/private-documents-bucket.yml \
  --parameter-overrides BucketName=YOUR-UNIQUE-STAGING-BUCKET AppIamUserName=YOUR-STAGING-IAM-USER
```

أنشئ مفاتيح IAM عبر قناة آمنة، خزّنها في Vercel Preview فقط، وتحقق من عدم وجود ACL أو سياسة عامة. لا تستخدم bucket الإنتاج أو بيانات حقيقية في اختبار staging.

## 3. ماسح ClamAV الخاص

يوفر `deploy/scanner/server.py` واجهة HTTP صغيرة تنفذ بروتوكول `POST /scan` الخام المتوقع من التطبيق، وتكلم ClamAV عبر شبكة Docker داخلية. لا تعرض منفذ ClamAV `3310` للإنترنت. اربط المنفذ المحلي `127.0.0.1:8081` فقط، ثم ضع `deploy/scanner/nginx.conf.example` في Reverse Proxy مع شهادة TLS موثوقة. استخدم Token عشوائيًا طويلًا وWAF/حدود طلبات على مضيف الماسح.

على مضيف ماسح مخصص، اختر نسخة ClamAV محدثة وراجع مصدرها ثم ثبّت digest غير قابل للتغيير؛ لا تستخدم tag متحركًا في التشغيل:

```bash
export CLAMAV_IMAGE='clamav/clamav@sha256:REPLACE_WITH_REVIEWED_DIGEST'
export DOCUMENT_SCANNER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose -f deploy/scanner/docker-compose.scanner.yml up -d --build
```

استبدل `REPLACE_WITH_REVIEWED_DIGEST` بـdigest حقيقي من سجل موثوق قبل التنفيذ؛ القالب يرفض قيمة غير مضبوطة.

ثبّت تحديثات توقيعات ClamAV وتابع `/ready`. اربط HTTPS من Nginx، ثم ضع عنوان HTTPS والـToken في Vercel Preview. قيد الوصول للمضيف وفق إمكانات الشبكة المتاحة، ولا ترسل مستندات حقيقية إلى خدمة فحص عامة.

بعد نشر الماسح التجريبي فقط، اختبر ملف EICAR القياسي دون رفعه إلى S3:

```bash
DOCUMENT_SCANNER_URL=https://scanner-staging.example.com/scan \
DOCUMENT_SCANNER_TOKEN='***' \
python scripts/verify_external_scanner.py
```

ينبغي أن يقبل الملف التجريبي النظيف، ويرفض EICAR بإجابة صريحة `{"clean": false}`. تغطي الاختبارات المحلية أيضًا حالة توقف الماسح؛ يجب أن تفشل عملية رفع المستند بـ503 وألا يُكتب أي كائن إلى S3. لا يُعد الاختبار ناجحًا لمجرد أن endpoint يرد؛ يجب التأكد من وجود ClamAV حقيقي ومحدّث.

## 4. WAF وحدود الطلبات

### Vercel

اضبط القواعد من Vercel Firewall للمشروع/نطاق staging؛ لا يستطيع ملف `vercel.json` إنشاء قواعد Firewall أو تجاوز إعدادات الحساب. على الأقل:

1. تفعيل Managed Ruleset متاح في الخطة للحماية من OWASP وطلبات الاستغلال الشائعة، مع وضع المراقبة أولًا ثم الحظر بعد مراجعة false positives.
2. Rate limit لعمليات `/api/v1/auth/login` و`/api/v1/auth/mfa/*` لكل IP، وتحدٍ/حظر للحركة الآلية غير الطبيعية. التطبيق يضيف حدًا مشتركًا لكل حساب، لكنه لا يعوض WAF ضد تبديل الحسابات أو الهجمات الموزعة.
3. Rate limit لرفع `/api/v1/documents`، وتطبيق سقف جسم الطلب الحالي 3 MiB على Vercel. لا تسمح بتجاوز TLS أو caching لواجهات API.
4. احتفظ بقواعد مختلفة لـstaging والإنتاج، وابدأ بـstaging. لا تضع قيود بلد أو حظرًا قد يوقف مستخدمين شرعيين قبل موافقة المؤسسة.
5. راقب محاولات الدخول المحظورة وطلبات WAF وسجل التنبيهات بعد كل تعديل.

### Docker البديل

تم توسيع `deploy/nginx.conf` بحدود IP لمعدل API وتسجيل الدخول، وحدود الاتصالات، وTLS 1.2+ وترويسات أساسية. أبق المنفذين 8000 و5432 داخليين، ولا تثق بـ`X-Forwarded-For` من العميل مباشرة.

## 5. المراقبة والتنبيه

يصدر التطبيق سجلات JSON لطلبات HTTP تتضمن request ID والطريق والحالة والزمن، من دون جسم الطلب أو بيانات الاعتماد أو عنوان IP. اجمع stdout/stderr في مزود الاستضافة، وأرسل تنبيهات على أخطاء 5xx وتأخر الخدمة ومحاولات الدخول غير الطبيعية وفشل نسخ الاحتياطيات. `/health` يختبر نبض التطبيق و`/ready` اتصال قاعدة البيانات.

الـworkflow `.github/workflows/staging-monitor.yml` يفحص `/health` و`/ready` كل 15 دقيقة أو يدويًا. عند الفشل، يرسل تنبيهًا اختياريًا عبر `ALERT_WEBHOOK_URL` ويترك GitHub Actions run فاشلًا للتنبيه. هذا ليس بديلًا عن مراقبة مزود الاستضافة أو لوحة WAF.

## 6. حدود التنفيذ الحالي

إنشاء مشروع Vercel/AWS، إضافة الأسرار، ربط DNS/TLS، تشغيل ClamAV وتنزيل تحديثاته، ضبط WAF، ومشاهدة نجاح deploy تتطلب حسابات وصلاحيات تشغيلية خارج Git. بعد إكمال هذه الخطوات، يجب حفظ رابط run ونتيجة فحص EICAR والاستعادة في سجل قبول UAT، لا الاكتفاء بوجود ملفات الإعداد في المستودع.
