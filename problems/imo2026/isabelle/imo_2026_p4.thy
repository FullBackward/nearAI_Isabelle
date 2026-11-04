theory imo_2026_p4
  imports Complex_Main "HOL-Library.Multiset"
begin

section \<open>IMO 2026, Problem 4 (Shan-Yu and Mulan cut a paper triangle)\<close>

text \<open>A triangle, viewed as the multiset of its three interior angles (in
degrees): positive reals summing to \<open>180\<close>.\<close>

definition is_triangle :: "real multiset \<Rightarrow> bool" where
  "is_triangle s \<longleftrightarrow> size s = 3 \<and> (\<forall>x \<in># s. 0 < x) \<and> sum_mset s = 180"

text \<open>A triangle \<open>s\<close> has an interior angle equal to \<open>\<theta>\<close>.\<close>

definition has_angle :: "real \<Rightarrow> real multiset \<Rightarrow> bool" where
  "has_angle \<theta> s \<longleftrightarrow> \<theta> \<in># s"

text \<open>One admissible cut of the triangle \<open>s\<close>, producing children \<open>L\<close> and \<open>R\<close>.

We pick an apex angle \<open>\<alpha>\<close> and the two base angles \<open>\<beta>, \<gamma>\<close> (so
\<open>s = {\<alpha>, \<beta>, \<gamma>}\<close>), and a cut parameter \<open>x\<close> in the open interval
\<open>(\<gamma>, 180 - \<beta>)\<close>.  The resulting two triangles have angle multisets
\<open>L = {\<beta>, x, 180 - \<beta> - x}\<close> and \<open>R = {\<gamma>, 180 - x, x - \<gamma>}\<close>.  Ranging over all
\<open>\<alpha>, \<beta>, \<gamma>\<close> with \<open>s = {\<alpha>, \<beta>, \<gamma>}\<close> captures all three apex choices and both
assignments of the two base angles.\<close>

definition is_cut :: "real multiset \<Rightarrow> real multiset \<Rightarrow> real multiset \<Rightarrow> bool" where
  "is_cut s L R \<longleftrightarrow>
     (\<exists>\<alpha> \<beta> \<gamma> x :: real.
        s = {#\<alpha>, \<beta>, \<gamma>#} \<and> \<gamma> < x \<and> x < 180 - \<beta> \<and>
        L = {#\<beta>, x, 180 - \<beta> - x#} \<and> R = {#\<gamma>, 180 - x, x - \<gamma>#})"

text \<open>The set of triangles from which Mulan can force, in finitely many steps,
a triangle with an interior angle equal to \<open>\<theta>\<close>, no matter how Shan-Yu
discards.  This is the least predicate closed under:

  * (\<open>win\<close>) if the current triangle already has an angle equal to \<open>\<theta>\<close>,
    Mulan has won;
  * (\<open>move\<close>) if Mulan can make a cut producing children \<open>L\<close> and \<open>R\<close> from
    \<^emph>\<open>both\<close> of which she wins (so whichever one Shan-Yu keeps, she still
    wins), then she wins from the current triangle.

Membership means Mulan wins in finitely many steps.\<close>

inductive mulan_wins :: "real \<Rightarrow> real multiset \<Rightarrow> bool" for \<theta> :: real where
  win:  "has_angle \<theta> s \<Longrightarrow> mulan_wins \<theta> s"
| move: "is_cut s L R \<Longrightarrow> mulan_wins \<theta> L \<Longrightarrow> mulan_wins \<theta> R \<Longrightarrow> mulan_wins \<theta> s"

text \<open>Mulan can guarantee victory for the value \<open>\<theta>\<close>: from every valid starting
triangle she wins in finitely many steps regardless of Shan-Yu's play.\<close>

definition mulan_can_guarantee :: "real \<Rightarrow> bool" where
  "mulan_can_guarantee \<theta> \<longleftrightarrow> (\<forall>s. is_triangle s \<longrightarrow> mulan_wins \<theta> s)"

text \<open>\<^bold>\<open>Main theorem.\<close>  For \<open>0 < \<theta> < 180\<close>, Mulan can guarantee her victory
in finitely many steps, no matter how Shan-Yu plays, if and only if
\<open>\<theta> = 180 / n\<close> for some integer \<open>n \<ge> 2\<close>.\<close>

theorem main_theorem:
  fixes \<theta> :: real
  assumes "0 < \<theta>" and "\<theta> < 180"
  shows "mulan_can_guarantee \<theta> \<longleftrightarrow> (\<exists>n :: nat. 2 \<le> n \<and> \<theta> = 180 / real n)"
  sorry

end
