# Native video upscale default

Official audited API default1080p upscaling means Google native promotion.
Omittedoperation on /videos/upscale selects promotion. Explicitoperation=export keeps
legacy localdownload/export; /videos/gif stays export270p. No source generation changes.

Scenarios: defaultpromotes1080p; explicitexportdoesnotbill nativepromotion; disabledvideo
403beforequeue; exactalias scope/defaultprovider controls preserve; malformedoperation422;
GIFunchanged; exportprovidercontrols501. Optional callbackimageonly5seconds, others10.

Plan: meaningful HTTP RED tests, one endpoint default selection edit, focused regressions.
Root sole livecaller. No paidliveverification or blanket reliabilitychanges.
