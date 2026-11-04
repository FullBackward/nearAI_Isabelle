theory imo_2026_p2
  imports "HOL-Analysis.Analysis"
begin

section \<open>IMO 2026, Problem 2 (circumcentre of AKL is equidistant from the midpoints)\<close>

text \<open>We work in the Euclidean plane: the type \<open>real^2\<close> with the standard
inner product, norm and distance (Lean: \<open>EuclideanSpace \<real> (Fin 2)\<close>).\<close>

type_synonym plane = "real^2"

text \<open>A point \<open>P\<close> lies in the open interior of the triangle \<open>X Y Z\<close>: it is a
strictly convex combination \<open>P = \<alpha> X + \<beta> Y + \<gamma> Z\<close> with \<open>\<alpha>, \<beta>, \<gamma> > 0\<close> and
\<open>\<alpha> + \<beta> + \<gamma> = 1\<close>.\<close>

definition inside_triangle :: "plane \<Rightarrow> plane \<Rightarrow> plane \<Rightarrow> plane \<Rightarrow> bool" where
  "inside_triangle X Y Z P \<longleftrightarrow>
     (\<exists>\<alpha> \<beta> \<gamma> :: real. 0 < \<alpha> \<and> 0 < \<beta> \<and> 0 < \<gamma> \<and> \<alpha> + \<beta> + \<gamma> = 1 \<and>
        P = \<alpha> *\<^sub>R X + \<beta> *\<^sub>R Y + \<gamma> *\<^sub>R Z)"

text \<open>A point \<open>P\<close> lies inside the (proper) angle at vertex \<open>Y\<close> spanned by the
rays \<open>Y X\<close> and \<open>Y Z\<close>: writing \<open>P - Y = s (X - Y) + t (Z - Y)\<close>, one has
\<open>s > 0\<close> and \<open>t > 0\<close>.\<close>

definition inside_angle :: "plane \<Rightarrow> plane \<Rightarrow> plane \<Rightarrow> plane \<Rightarrow> bool" where
  "inside_angle X Y Z P \<longleftrightarrow>
     (\<exists>s t :: real. 0 < s \<and> 0 < t \<and> P - Y = s *\<^sub>R (X - Y) + t *\<^sub>R (Z - Y))"

text \<open>\<open>Oc\<close> is the circumcentre of triangle \<open>A K L\<close>: it is equidistant from the
three vertices.  (For a nondegenerate triangle such a point exists and is
unique.)  The problem calls this point \<open>O\<close>; in Isabelle/HOL \<open>O\<close> is the
infix for relation composition and cannot be a variable, hence \<open>Oc\<close>.\<close>

definition is_circumcentre :: "plane \<Rightarrow> plane \<Rightarrow> plane \<Rightarrow> plane \<Rightarrow> bool" where
  "is_circumcentre A K L Oc \<longleftrightarrow> dist Oc A = dist Oc K \<and> dist Oc A = dist Oc L"

text \<open>The unoriented angle between two vectors and the unoriented angle
\<open>angle P Q R\<close> at the vertex \<open>Q\<close> between the rays \<open>Q P\<close> and \<open>Q R\<close>, exactly as
Mathlib's \<open>InnerProductGeometry.angle\<close> / \<open>EuclideanGeometry.angle\<close>:
\<open>arccos\<close> of the normalised inner product.  (When a vector is \<open>0\<close> the
quotient is \<open>0\<close> in both systems, so the angle is \<open>pi/2\<close>.)\<close>

definition vangle :: "plane \<Rightarrow> plane \<Rightarrow> real" where
  "vangle u v = arccos ((u \<bullet> v) / (norm u * norm v))"

definition angle :: "plane \<Rightarrow> plane \<Rightarrow> plane \<Rightarrow> real" where
  "angle P Q R = vangle (P - Q) (R - Q)"

text \<open>\<^bold>\<open>Main theorem.\<close>  With the configuration described above, the
circumcentre \<open>Oc\<close> of triangle \<open>AKL\<close> satisfies \<open>OM = ON\<close>, where \<open>M\<close>, \<open>N\<close> are
the midpoints of \<open>AB\<close>, \<open>AC\<close>.\<close>

theorem main_theorem:
  fixes A B C K L Oc M N :: plane
  assumes "\<not> collinear {A, B, C}"
    and "M = midpoint A B" and "N = midpoint A C"
    and "inside_triangle B M C K" and "inside_triangle B N C L"
    and "inside_angle L B A K" and "inside_angle A C K L"
    and "angle K B A = angle A C L"
    and "angle L B K = angle L N C"
    and "angle L C K = angle B M K"
    and "is_circumcentre A K L Oc"
  shows "dist Oc M = dist Oc N"
  sorry

end
