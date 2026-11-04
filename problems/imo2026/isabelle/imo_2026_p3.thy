theory imo_2026_p3
  imports Complex_Main
begin

section \<open>IMO 2026, Problem 3 (Liu Bang and Xiang Yu divide a stick)\<close>

text \<open>The list of piece lengths obtained by cutting \<open>[0,1]\<close> at the points of a
finite set \<open>S \<subseteq> (0,1)\<close>: sort \<open>S\<close> ascending, prepend \<open>0\<close>, append \<open>1\<close>, and
take consecutive differences.  The result has \<open>|S| + 1\<close> positive entries
summing to \<open>1\<close> (when \<open>S \<subseteq> (0,1)\<close>).\<close>

definition piece_lengths :: "real set \<Rightarrow> real list" where
  "piece_lengths S = (let l = 0 # sorted_list_of_set S @ [1]
                      in map (\<lambda>(a, b). b - a) (zip l (tl l)))"

text \<open>The sum of the entries of a list \<open>L\<close> at the (0-indexed) even positions
after sorting \<open>L\<close> in non-increasing order: the pieces claimed by the first
mover under the greedy claiming rule (the 1st, 3rd, 5th, \<dots> largest).\<close>

definition first_player_share :: "real list \<Rightarrow> real" where
  "first_player_share L = (let s = rev (sort L)
                           in sum_list (map (\<lambda>i. s ! i) (filter even [0..<length s])))"

text \<open>\<open>liu_share A B\<close>: Liu Bang's total length, given Liu Bang's marks \<open>A\<close> and
Xiang Yu's marks \<open>B\<close> (Lean: \<open>L A B\<close>).\<close>

definition liu_share :: "real set \<Rightarrow> real set \<Rightarrow> real" where
  "liu_share A B = first_player_share (piece_lengths (A \<union> B))"

text \<open>An admissible marking for a player: a finite subset of \<open>(0,1)\<close> of size at
most \<open>n\<close>.\<close>

definition admissible_mark :: "nat \<Rightarrow> real set \<Rightarrow> bool" where
  "admissible_mark n X \<longleftrightarrow> finite X \<and> X \<subseteq> {0<..<1} \<and> card X \<le> n"

text \<open>The value Liu Bang can guarantee: the supremum over Liu Bang's admissible
markings \<open>A\<close> of the infimum, over Xiang Yu's admissible markings \<open>B\<close> disjoint
from \<open>A\<close>, of \<open>liu_share A B\<close>.\<close>

definition V :: "nat \<Rightarrow> real" where
  "V n = Sup ((\<lambda>A. Inf ((\<lambda>B. liu_share A B) ` {B. admissible_mark n B \<and> A \<inter> B = {}}))
              ` {A. admissible_mark n A})"

subsection \<open>Correctness statements for the definitions\<close>

text \<open>The piece lengths of an admissible cut set sum to \<open>1\<close>.\<close>

theorem piece_lengths_sum:
  assumes "finite S" and "S \<subseteq> {0<..<1}"
  shows "sum_list (piece_lengths S) = 1"
  sorry

text \<open>There are \<open>|S| + 1\<close> pieces.\<close>

theorem piece_lengths_length:
  assumes "finite S"
  shows "length (piece_lengths S) = card S + 1"
  sorry

text \<open>Liu Bang's share lies in \<open>[0, 1]\<close> for admissible cut sets.\<close>

theorem liu_share_mem_Icc:
  assumes "finite A" and "finite B" and "A \<subseteq> {0<..<1}" and "B \<subseteq> {0<..<1}"
  shows "liu_share A B \<in> {0..1}"
  sorry

subsection \<open>Main statements\<close>

text \<open>\<^bold>\<open>Main statement.\<close>  For every positive integer \<open>n\<close>, Liu Bang's
guaranteed value equals \<open>2^n / (2^(n+1) - 1)\<close>.\<close>

theorem V_eq:
  assumes "0 < n"
  shows "V n = (2::real) ^ n / ((2::real) ^ (n + 1) - 1)"
  sorry

text \<open>\<^bold>\<open>Lower bound.\<close>  Liu Bang has an admissible marking \<open>A\<close> such that for
every admissible marking \<open>B\<close> disjoint from \<open>A\<close>, his share is at least
\<open>2^n / (2^(n+1) - 1)\<close>.\<close>

theorem lower_bound:
  assumes "0 < n"
  shows "\<exists>A. admissible_mark n A \<and>
           (\<forall>B. admissible_mark n B \<longrightarrow> A \<inter> B = {} \<longrightarrow>
                 (2::real) ^ n / ((2::real) ^ (n + 1) - 1) \<le> liu_share A B)"
  sorry

text \<open>\<^bold>\<open>Upper bound / optimality.\<close>  For every admissible marking \<open>A\<close> of Liu
Bang, Xiang Yu has an admissible marking \<open>B\<close> disjoint from \<open>A\<close> with
\<open>liu_share A B \<le> 2^n / (2^(n+1) - 1)\<close>, so Liu Bang cannot guarantee more.\<close>

theorem upper_bound:
  assumes "0 < n"
  shows "\<forall>A. admissible_mark n A \<longrightarrow>
           (\<exists>B. admissible_mark n B \<and> A \<inter> B = {} \<and>
                 liu_share A B \<le> (2::real) ^ n / ((2::real) ^ (n + 1) - 1))"
  sorry

end
