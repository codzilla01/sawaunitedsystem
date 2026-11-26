# تقرير التحقق — SAWA UNITED BMS

## نتيجة التشغيل المحلي

آخر تشغيل لهذه النسخة من المستودع: **45 passed, 5 skipped, 1 warning** على Python 3.11 وSQLite. الاختبارات الخمسة المتخطاة هي اختبارات PostgreSQL الفعلية في `tests/test_postgres_integration.py`؛ تحتاج `TEST_POSTGRES_URL` بعد تطبيق migrations. ظهر تحذير deprecation من `starlette.testclient` مع httpx، ولم يمنع النجاح. فحص `python -m compileall -q app api scripts tests` نجح.

> **هذا ليس تقرير قبول PostgreSQL أو staging.** لا يتوفر Docker أو PostgreSQL محليًا. أول تشغيل لـGitHub Actions على `212ac53` نجح في اختبارات SQLite وتطبيق migrations `0001`–`0003`، لكنه فشل في خطوة اختبارات PostgreSQL؛ أضيفت الآن مخرجات فشل كتعليقات تشخيصية لإعادة التشغيل. فشل كذلك فحص Vercel Preview التلقائي، ولا تعتبر أي من الحالتين نشرًا ناجحًا.

## نطاق الاختبارات المضافة/الموجودة

- تسجيل الدخول، تدفق إعداد MFA، TOTP صحيح/خاطئ، ومنع إعادة استخدام الرمز.
- صلاحيات الأدوار ونطاق النشاط ومسارات العمل الرئيسية.
- رفض المستند المصاب (EICAR mock)، وفشل الماسح المغلق عند الانقطاع، وعدم كتابة الملف إلى S3 عند الرفض.
- أمان إعدادات الإنتاج، CSRF، readiness headers، ومفتاح MFA.
- تزامن إكمال الطلبات الغذائية عبر row locks، وقيود الحجز الزمنية، واختبارات عزل API على PostgreSQL — هذه الأخيرة متاحة للـCI لكنها غير منفذة محليًا.
- Workflow CI يطبق migrations 0001–0003 على PostgreSQL 16، ثم يشغّل اختبارات PostgreSQL للتزامن والصلاحيات، وفحص بدء الإنتاج، و`pg_dump`/`pg_restore` إلى قاعدة اختبار منفصلة.

## ما لم يُثبت بعد

- نجاح GitHub Actions فعليًا على Python 3.12/PostgreSQL 16.
- نشر Vercel Preview ونجاح `/health` و`/ready` على خدمة مستضافة.
- نجاح EICAR ضد ClamAV فعلي محدث؛ `scripts/verify_external_scanner.py` ينتظر ماسح staging حقيقيًا.
- أمان إعداد AWS/S3 الخاص وسياسة IAM في حساب فعلي، واستعادة نسخة إنتاج/تجربة خارج بيئة CI.
- اختبار اختراق خارجي أو حمل/P95 أو مراجعة OWASP مستقلة.
- UAT وموافقات مسؤولي الأنشطة، المالية، القانونية، وحماية البيانات.

لإكمال هذه النقاط، استخدم `docs/staging-hardening-ar.md` و`docs/uat-acceptance-ar.md`، وسجل نتائج Actions واختبار EICAR والاستعادة والتواقيع الرسمية قبل Go-Live.
