*** Begin Patch
*** Update File: app/contest_engine.py
@@
     contest.config['knockout_matches_female'] = female_matches
     contest.config['knockout_matches_male'] = male_matches
     contest.config['female_top16'] = female_top16
     contest.config['male_top16'] = male_top16
+    # 保存历史快照：初始 16 强，用于后续最终排名的历史回溯
+    contest.config['knockout_matches_female_round16'] = female_matches.copy()
+    contest.config['knockout_matches_male_round16'] = male_matches.copy()
+    flag_modified(contest, 'config')
*** End Patch
