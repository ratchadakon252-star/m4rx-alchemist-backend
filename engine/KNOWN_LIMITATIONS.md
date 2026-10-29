# Known Limitations — P4
1. ไม่มีnativeOHLCจริงหรือindependentgroundtruthใหม่. P3ยังPARTIAL;real-input60runsทั้งหมดDATA_UNVERIFIEDและ0pricedplans. ไม่พิสูจน์NO_TRADE/false-rejectionดีขึ้น.
2. Screenshotadapterเป็นcuratedfacts/bbox/uncertaintyconsumer ไม่ใช่generalOCRหรือexactpixel→OHLC. ProjectMarkdownไม่เรียกPythonเอง;manualmathต้องติดRuntimeMANUAL_REFERENCE.
3. P4เปิด4cardsเฉพาะscope:MC04POI,MC05iFVGclosedinversion,MC07FVG-linkedBreaker,MC08containedUnicorn. P3compatibilityAPIคง3cards;ใช้alchemist_appสำหรับP4scope. MC03genericContinuationยังdisabled;MC05continuationlabelเฉพาะเมื่อมีconfirmedM15trendไม่ใช่เปิดMC03.
4. Mode3มีrouter/assetguardแต่ไม่มีapprovedindexprofile จึงBLOCKED. Mode5M1refinementเป็นguardedcomposition ไม่ใช่fullbookstrategy;H1optional,M15/M5/M1และchronology/nativeaggregationrequired,SLยังM5. Mode4/5ทั้งสองฝั่งแยกผลและไม่บังคับต้องtradeทั้งคู่.
5. P4nativeHTFfreshnessguardบล็อกstaleH1/M15จากcurrenttradeและยังเก็บdiagnosticcompletion. เป็นoperationalqualitypolicy ไม่ใช่sourcealpha;ตลาด/sessioncalendarเฉพาะvenueยังไม่เชื่อม.
6. Strict3-barconfirmedpivots,visibleFVGs/targets/barriersและlatest-swingvariantอาจไม่ครอบทุกpattern/HTFarray. CompleteScanหมายถึงenabledvisiblevariantsในspanเท่านั้น ไม่ใช่ทั้งตลาดหรือknowledgeทั้งหมด.
7. Independentvalidatorคำนวณmath/rawrefsซ้ำแต่ไม่ใช่independentperception. Hashยืนยันbytesไม่ยืนยันว่าข้อมูลfeed/manualannotationจริงถูกต้อง.
8. Targetsผูกตอนformation;targettakenก่อนentryทำexpire. Mode5M5retestก่อนM1proofไม่ถูกนับเป็นfilledMode5order;newM1POIต้องfreshหลังproof. Intrabarfill/P&Lยังไม่มีbacktester;used/expiredไม่ใช่ชนะ/แพ้.
9. Brokerfields/lot/maxloss/netRRยังUNKNOWN;1M4RXpoint=.01nativeXAUเป็นหน่วยงานทดสอบไม่ใช่brokertick. Preferred270–355/500–1000ไม่เป็นhardSL/TPpricefabricator. RRthresholdsยังPROVISIONAL.
10. LegacyJournalTRADEไม่เป็นvalidatedtradeโดยอัตโนมัติ;v2migrationเก็บreportedlegacyและต้องrevalidate. ยังไม่มีactualJournalimporterE2Eหรือpersistentjournalservice.
11. Sourcebookตรวจเฉพาะpagesในcards/report;338assets/337headings/46chaptersไม่เท่ากับreviewครบ. ฐานความรู้อื่นยังอยู่originalattachmentและinventory/backlog ไม่ถูกบรรจุซ้ำทั้งหมดในP4zip.
12. Projectinstructionsเป็นเอกสารนำเข้าProject ไม่ใช่personalSkillที่ติดตั้งแล้ว. Static/localCLItestไม่เท่ากับindependentin-Projectforwardtest. ไม่claimKnowledgeComplete/FinalRelease/LiveReady.
13. P2/P3originalcode/cards/dataยังอยู่ในimmutableP3→P2archive. ActiveP4workingcopiesมีdiff/versionและsubcheckpoints;ไม่แก้baseline.
