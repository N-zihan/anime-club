*** Begin Patch
*** Update File: app/contest_engine.py
@@
     if phase == 'knockout_16_result' and now >= times['knockout_16_result_end'] and contest.status == 'knockout':
         female_matches = contest.config.get('knockout_matches_female', [])
         male_matches = contest.config.get('knockout_matches_male', [])
         if female_matches:
-            contest.config['knockout_matches_female'] = generate_next_round(contest, female_matches, 'female', 1, '8强')
+            # 在生成 8 强之前，保存 8 强历史快照
+            next_female = generate_next_round(contest, female_matches, 'female', 1, '8强')
+            contest.config['knockout_matches_female_round8'] = next_female.copy()
+            contest.config['knockout_matches_female'] = next_female
         if male_matches:
-            contest.config['knockout_matches_male'] = generate_next_round(contest, male_matches, 'male', 1, '8强')
+            next_male = generate_next_round(contest, male_matches, 'male', 1, '8强')
+            contest.config['knockout_matches_male_round8'] = next_male.copy()
+            contest.config['knockout_matches_male'] = next_male
         flag_modified(contest, 'config')
         db.session.commit()
         return True, '8强'
@@
     elif phase == 'knockout_8_result' and now >= times['knockout_8_result_end'] and contest.status == 'knockout':
         female_matches = contest.config.get('knockout_matches_female', [])
         male_matches = contest.config.get('knockout_matches_male', [])
         if female_matches:
-            contest.config['knockout_matches_female'] = generate_next_round(contest, female_matches, 'female', 2, '4强')
+            next_female = generate_next_round(contest, female_matches, 'female', 2, '4强')
+            contest.config['knockout_matches_female_round4'] = next_female.copy()
+            contest.config['knockout_matches_female'] = next_female
         if male_matches:
-            contest.config['knockout_matches_male'] = generate_next_round(contest, male_matches, 'male', 2, '4强')
+            next_male = generate_next_round(contest, male_matches, 'male', 2, '4强')
+            contest.config['knockout_matches_male_round4'] = next_male.copy()
+            contest.config['knockout_matches_male'] = next_male
         flag_modified(contest, 'config')
         db.session.commit()
         return True, '4强'
@@
     elif phase == 'knockout_4_result' and now >= times['knockout_4_result_end'] and contest.status == 'knockout':
         female_matches = contest.config.get('knockout_matches_female', [])
         male_matches = contest.config.get('knockout_matches_male', [])
         if female_matches:
-            contest.config['knockout_matches_female'] = generate_next_round(contest, female_matches, 'female', 3,
-                                                                            '决赛')
+            next_female = generate_next_round(contest, female_matches, 'female', 3, '决赛')
+            contest.config['knockout_matches_female_final'] = next_female.copy()
+            contest.config['knockout_matches_female'] = next_female
         if male_matches:
-            contest.config['knockout_matches_male'] = generate_next_round(contest, male_matches, 'male', 3, '决赛')
+            next_male = generate_next_round(contest, male_matches, 'male', 3, '决赛')
+            contest.config['knockout_matches_male_final'] = next_male.copy()
+            contest.config['knockout_matches_male'] = next_male
         flag_modified(contest, 'config')
         db.session.commit()
         return True, '决赛'
*** End Patch
