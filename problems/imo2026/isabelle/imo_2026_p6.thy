theory imo_2026_p6
  imports Main
begin

section \<open>IMO 2026, Problem 6 (eventual periodicity of a gcd-greedy sequence)\<close>

text \<open>The sequence is 0-indexed (\<open>a 0\<close> is \<open>a_1\<close>).  \<open>is_valid_seq a\<close> says: each
term exceeds \<open>1\<close>, and each subsequent term is the smallest integer strictly
larger than the previous one that shares a common factor with every earlier
term.\<close>

definition is_valid_seq :: "(nat \<Rightarrow> nat) \<Rightarrow> bool" where
  "is_valid_seq a \<longleftrightarrow>
     (\<forall>n. 1 < a n) \<and>
     (\<forall>n. a n < a (n + 1) \<and>
          (\<forall>i \<le> n. 1 < gcd (a (n + 1)) (a i)) \<and>
          (\<forall>b. a n < b \<longrightarrow> b < a (n + 1) \<longrightarrow> (\<exists>i \<le> n. gcd b (a i) = 1)))"

text \<open>\<^bold>\<open>Main theorem.\<close>  For any such sequence there exist positive integers
\<open>T\<close> and \<open>L\<close> with \<open>a (n + T) = a n + L\<close> for every \<open>n\<close>; equivalently, the
sequence of consecutive differences is purely periodic.\<close>

theorem main_theorem:
  fixes a :: "nat \<Rightarrow> nat"
  assumes "is_valid_seq a"
  shows "\<exists>T L :: nat. 0 < T \<and> 0 < L \<and> (\<forall>n. a (n + T) = a n + L)"
  sorry

end
