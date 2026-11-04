theory imo_2026_p5
  imports Complex_Main
begin

section \<open>IMO 2026, Problem 5 (a functional inequality on the positive reals)\<close>

text \<open>Lean works with the subtype of positive reals.  Here \<open>f :: real \<Rightarrow> real\<close>
is only ever evaluated at positive arguments, and the theorem assumes \<open>f\<close>
maps positive reals to positive reals; the inequality is required for all
positive \<open>x, y\<close>.\<close>

definition is_admissible :: "(real \<Rightarrow> real) \<Rightarrow> bool" where
  "is_admissible f \<longleftrightarrow>
     (\<forall>x y :: real. 0 < x \<longrightarrow> 0 < y \<longrightarrow>
        sqrt ((x\<^sup>2 + (f y)\<^sup>2) / 2) \<ge> (f x + y) / 2 \<and>
        (f x + y) / 2 \<ge> sqrt (x * f y))"

theorem main_theorem:
  fixes f :: "real \<Rightarrow> real"
  assumes "\<forall>x :: real. 0 < x \<longrightarrow> 0 < f x"
  shows "is_admissible f \<longleftrightarrow> (\<exists>c :: real. 0 \<le> c \<and> (\<forall>x :: real. 0 < x \<longrightarrow> f x = x + c))"
  sorry

end
