'''
Created on Feb 13, 2014

@author: maxzwiessele
'''
import unittest
import numpy as np

from ..core.observable_array import ObsAr
from ..core.index_operations import ParameterIndexOperations
from ..core.nameable import adjust_name_for_printing
from ..core import HierarchyError
from paramz import transformations
from ..parameterized import Parameterized
from ..param import Param
from ..model import Model

class ArrayCoreTest(unittest.TestCase):
    def setUp(self):
        self.X = np.random.normal(1,1, size=(100,10))
        self.obsX = ObsAr(self.X)

    def test_init(self):
        X = ObsAr(self.X)
        X2 = ObsAr(X)
        self.assertIs(X, X2, "no new Observable array, when Observable is given")

    def test_slice(self):
        t1 = self.X[2:78]
        t2 = self.obsX[2:78]
        self.assertListEqual(t1.tolist(), t2.tolist(), "Slicing should be the exact same, as in ndarray")


def test_constraints_in_init():
    class Test(Parameterized):
        def __init__(self, name=None, parameters=[], *a, **kw):
            super(Test, self).__init__(name=name)
            self.x = Param('x', np.random.uniform(0,1,(3,4)))
            self.x[0].constrain_bounded(0,1)
            self.link_parameter(self.x)
            self.x[1].fix()
    t = Test()
    c = {transformations.Logistic(0,1): np.array([0, 1, 2, 3]), 'fixed': np.array([4, 5, 6, 7])}
    np.testing.assert_equal(t.x.constraints[transformations.Logistic(0,1)], c[transformations.Logistic(0,1)])
    np.testing.assert_equal(t.x.constraints['fixed'], c['fixed'])

def test_parameter_modify_in_init():
    class TestLikelihood(Parameterized):
        def __init__(self, param1 = 2., param2 = 3.):
            super(TestLikelihood, self).__init__("TestLike")
            self.p1 = Param('param1', param1)
            self.p2 = Param('param2', param2)

            self.link_parameter(self.p1)
            self.link_parameter(self.p2)

            self.p1.fix()
            self.p1.unfix()
            self.p2.constrain_negative()
            self.p1.fix()
            self.p2.constrain_positive()
            self.p2.fix()
            self.p2.constrain_positive()

    m = TestLikelihood()
    print(m)
    val = m.p1.values.copy()
    assert(m.p1.is_fixed)
    assert(m.constraints[transformations.Logexp()].tolist() == [1])
    m.randomize()
    assert(m.p1 == val)


class P(Parameterized):
    def __init__(self, name, **kwargs):
        super(P, self).__init__(name=name)
        for k, val in kwargs.items():
            self.__setattr__(k, val)
            self.link_parameter(self.__getattribute__(k))

class ModelTest(unittest.TestCase):

    def setUp(self):
        class M(Model):
            def __init__(self, name, **kwargs):
                super(M, self).__init__(name=name)
                for k, val in kwargs.items():
                    self.__setattr__(k, val)
                    self.link_parameter(self.__getattribute__(k))
            def objective_function(self):
                return self._obj
            def parameters_changed(self):
                self._obj = (self.param_array**2).sum()
                self.gradient[:] = 2*self.param_array
        
        self.testmodel = M('testmodel')
        self.testmodel.kern = P('rbf')
        self.testmodel.likelihood = P('Gaussian_noise', variance=Param('variance', np.random.uniform(0.1, 0.5), transformations.Logexp()))
        self.testmodel.link_parameter(self.testmodel.kern)
        self.testmodel.link_parameter(self.testmodel.likelihood)
        variance=Param('variance', np.random.uniform(0.1, 0.5), transformations.Logexp())
        lengthscale=Param('lengthscale', np.random.uniform(.1, 1, 1), transformations.Logexp())
        self.testmodel.kern.variance = variance
        self.testmodel.kern.lengthscale = lengthscale
        self.testmodel.kern.link_parameter(lengthscale)
        self.testmodel.kern.link_parameter(variance)
        #=============================================================================
        # GP_regression.           |  Value  |  Constraint  |  Prior  |  Tied to
        # rbf.variance             |    1.0  |     +ve      |         |
        # rbf.lengthscale          |    1.0  |     +ve      |         |
        # Gaussian_noise.variance  |    1.0  |     +ve      |         |
        #=============================================================================

    def test_optimize_preferred(self):
        self.testmodel.update_model(False)
        self.testmodel.optimize('lbfgs', messages=True, xtol=0, ftol=0, gtol=1e-6, bfgs_factor=1)
        np.testing.assert_array_less(self.testmodel.gradient, np.ones(self.testmodel.size)*1e-2)
    def test_optimize_scg(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.testmodel.optimize('scg', messages=1, max_f_eval=10)
        np.testing.assert_array_less(self.testmodel.gradient, np.ones(self.testmodel.size)*1e-1)
    def test_optimize_tnc(self):
        from ..optimization.optimization import opt_tnc
        self.testmodel.optimize_restarts(messages=1, optimizer=opt_tnc(self.testmodel.optimizer_array))
        np.testing.assert_array_less(self.testmodel.gradient, np.ones(self.testmodel.size)*1e-2)
    def test_optimize_org_bfgs(self):
        with np.errstate(divide='ignore'):
            self.testmodel.optimize_restarts(messages=1, optimizer='org-bfgs', xtol=0, ftol=0, gtol=1e-6)
        np.testing.assert_array_less(self.testmodel.gradient, np.ones(self.testmodel.size)*1e-2)
    def test_optimize_fix(self):
        self.testmodel.fix()
        self.testmodel.optimize(messages=1)
    def test_optimize_cgd(self):
        self.assertRaises(KeyError, self.testmodel.optimize, 'cgd', messages=1)
    def test_optimize_simplex(self):
        self.testmodel.optimize('simplex', messages=1, xtol=0, ftol=0, gtol=1e-6)
        np.testing.assert_array_less(self.testmodel.gradient, np.ones(self.testmodel.size)*1e-2)
        
    def test_raveled_index(self):
        self.assertListEqual(self.testmodel._raveled_index_for(self.testmodel['.*variance']).tolist(), [1, 2])

    def test_constraints_testmodel(self):
        self.testmodel.rbf.constrain_negative()
        self.assertListEqual(self.testmodel.constraints[transformations.NegativeLogexp()].tolist(), [0,1])

        self.testmodel.rbf.lengthscale.constrain_bounded(0,1)
        self.assertListEqual(self.testmodel.constraints[transformations.NegativeLogexp()].tolist(), [1])
        self.assertListEqual(self.testmodel.constraints[transformations.Logistic(0, 1)].tolist(), [0])

        self.testmodel.unconstrain_negative()
        self.assertListEqual(self.testmodel.constraints[transformations.NegativeLogexp()].tolist(), [])
        self.assertListEqual(self.testmodel.constraints[transformations.Logistic(0, 1)].tolist(), [0])

        self.testmodel.rbf.lengthscale.unconstrain_bounded(0,1)
        self.assertListEqual(self.testmodel.constraints[transformations.Logistic(0, 1)].tolist(), [])

    def test_updates(self):
        val = float(self.testmodel.objective_function())
        self.testmodel.update_model(False)
        self.testmodel.kern.randomize()
        self.testmodel.likelihood.randomize()
        self.assertEqual(val, self.testmodel.objective_function())
        self.testmodel.update_model(True)
        self.assertNotEqual(val, self.testmodel.objective_function())

    def test_fixing_optimize(self):
        self.testmodel.kern.lengthscale.fix()
        val = float(self.testmodel.kern.lengthscale)
        self.testmodel.randomize()
        self.assertEqual(val, self.testmodel.kern.lengthscale)

    def test_regular_expression_misc(self):
        self.testmodel.kern.lengthscale.fix()
        val = float(self.testmodel.kern.lengthscale)
        self.testmodel.randomize()
        self.assertEqual(val, self.testmodel.kern.lengthscale)

        variances = self.testmodel['.*var'].values()
        self.testmodel['.*var'].fix()
        self.testmodel.randomize()
        np.testing.assert_equal(variances, self.testmodel['.*var'].values())

    def test_fix_unfix(self):
        fixed = self.testmodel.kern.lengthscale.fix()
        self.assertListEqual(fixed.tolist(), [0])
        unfixed = self.testmodel.kern.lengthscale.unfix()
        self.testmodel.kern.lengthscale.constrain_positive()
        self.assertListEqual(unfixed.tolist(), [0])

        fixed = self.testmodel.kern.fix()
        self.assertListEqual(fixed.tolist(), [0,1])
        unfixed = self.testmodel.kern.unfix()
        self.assertListEqual(unfixed.tolist(), [0,1])

    def test_checkgrad(self):
        self.assertTrue(self.testmodel.checkgrad(1))
        self.assertTrue(self.testmodel.checkgrad())
        self.assertTrue(self.testmodel.rbf.variance.checkgrad(1))
        self.assertTrue(self.testmodel.rbf.variance.checkgrad())

    def test_printing(self):
        print(self.testmodel.hierarchy_name(False))

class ParameterizedTest(unittest.TestCase):

    def setUp(self):
        self.rbf = Parameterized('rbf')
        self.rbf.lengthscale = Param('lengthscale', np.random.uniform(.1, 1), transformations.Logexp())
        self.rbf.variance = Param('variance', np.random.uniform(0.1, 0.5), transformations.Logexp()) 
        self.rbf.link_parameters(self.rbf.variance, self.rbf.lengthscale)
        
        self.white = P('white', variance=Param('variance', np.random.uniform(0.1, 0.5), transformations.Logexp()))
        self.param = Param('param', np.random.uniform(0,1,(10,5)), transformations.Logistic(0, 1))

        self.test1 = Parameterized('test_parameterized')

        self.test1.param = self.param
        self.test1.kern = Parameterized('add')
        self.test1.kern.link_parameters(self.rbf, self.white)
        
        self.test1.link_parameter(self.test1.kern)
        self.test1.link_parameter(self.param, 0)

        # print self.test1:
        #=============================================================================
        # test_model.          |    Value    |  Constraint   |  Prior  |  Tied to
        # param                |  (25L, 2L)  |   {0.0,1.0}   |         |
        # add.rbf.variance     |        1.0  |  0.0,1.0 +ve  |         |
        # add.rbf.lengthscale  |        1.0  |  0.0,1.0 +ve  |         |
        # add.white.variance   |        1.0  |  0.0,1.0 +ve  |         |
        #=============================================================================

    def test_unfixed_param_array(self):
        self.test1.param_array[:] = 0.1
        np.testing.assert_array_equal(self.test1.unfixed_param_array, [0.1]*53)
        self.test1.unconstrain()
        self.test1.kern.rbf.lengthscale.fix()
        np.testing.assert_array_equal(self.test1.kern.unfixed_param_array, [0.1, 0.1])
        np.testing.assert_array_equal(self.test1.unfixed_param_array, [0.1]*52)
        
    def test_set_param_array(self):
        self.assertRaises(AttributeError, setattr, self.test1, 'param_array', 0)
    
    def test_fixed_optimizer_copy(self):
        self.test1[:] = 0.1
        self.test1.unconstrain()
        np.testing.assert_array_equal(self.test1.kern.white.optimizer_array, [0.1])
        self.test1.kern.fix()
        
        np.testing.assert_array_equal(self.test1.optimizer_array, [0.1]*50)
        np.testing.assert_array_equal(self.test1.optimizer_array, self.test1.param.optimizer_array)

        self.assertTrue(self.test1.kern.is_fixed)
        self.assertTrue(self.test1.kern.white.is_fixed)
        self.assertTrue(self.test1.kern.white._has_fixes())
        self.assertTrue(self.test1._has_fixes())

        np.testing.assert_array_equal(self.test1.kern.optimizer_array, [])
        np.testing.assert_array_equal(self.test1.kern.white.optimizer_array, [])

    def test_param_names(self):
        self.assertSequenceEqual(self.test1.kern.rbf._get_param_names_transformed().tolist(), ['test_parameterized.add.rbf.variance[[0]]', 'test_parameterized.add.rbf.lengthscale[[0]]'])

        self.test1.param.fix()
        self.test1.kern.rbf.lengthscale.fix()
        self.assertSequenceEqual(self.test1._get_param_names_transformed().tolist(), ['test_parameterized.add.rbf.variance[[0]]', 'test_parameterized.add.white.variance[[0]]'])
        
    def test_num_params(self):
        self.assertEqual(self.test1.num_params, 2)
        self.assertEqual(self.test1.add.num_params, 2)
        self.assertEqual(self.test1.add.white.num_params, 1)
        self.assertEqual(self.test1.add.rbf.num_params, 2)
        
    def test_index_operations(self):
        self.assertRaises(AttributeError, self.test1.add_index_operation, 'constraints', None)
        self.assertRaises(AttributeError, self.test1.remove_index_operation, 'not_an_index_operation')
        
    def test_names(self):
        self.test1.unlink_parameter(self.test1.kern)
        newname = 'this@is a+new name!'
        self.test1.kern.name = newname
        self.test1.link_parameter(self.test1.kern)
        self.assertSequenceEqual(self.test1.kern.name, newname)
        self.assertSequenceEqual(self.test1.kern.hierarchy_name(False), 'test_parameterized.'+newname)
        self.assertSequenceEqual(self.test1.kern.hierarchy_name(True), 'test_parameterized.'+adjust_name_for_printing(newname))
        self.assertRaises(NameError, adjust_name_for_printing, '%')
        
    def test_traverse_parents(self):
        c = []
        self.test1.kern.rbf.traverse_parents(lambda x: c.append(x.name))
        self.assertSequenceEqual(c, ['test_parameterized', 'param', 'add', 'white', 'variance'])
        c = []
        self.test1.kern.white.variance.traverse_parents(lambda x: c.append(x.name))
        self.assertSequenceEqual(c, ['test_parameterized', 'param', 'add', 'rbf', 'variance', 'lengthscale', 'white'])
        
    def test_names_already_exist(self):
        self.test1.kern.name = 'newname'
        self.test1.p = Param('newname', 1.22345)
        self.test1.link_parameter(self.test1.p)
        self.assertSequenceEqual(self.test1.kern.name, 'newname')
        self.assertSequenceEqual(self.test1.p.name, 'newname_1')
        self.test1.p2 = Param('newname', 1.22345)
        self.test1.link_parameter(self.test1.p2)
        self.assertSequenceEqual(self.test1.p2.name, 'newname_2')
        self.test1.kern.rbf.lengthscale.name = 'variance'
        self.assertSequenceEqual(self.test1.kern.rbf.lengthscale.name, 'variance_1')
        self.test1.kern.rbf.variance.name = 'variance_1'
        self.assertSequenceEqual(self.test1.kern.rbf.lengthscale.name, 'variance_2')
        self.test1.kern.rbf.variance.name = 'variance'
        self.assertSequenceEqual(self.test1.kern.rbf.lengthscale.name, 'variance_2')
        self.assertSequenceEqual(self.test1.kern.rbf.variance.name, 'variance')
        

    def test_add_parameter(self):
        self.assertEquals(self.rbf._parent_index_, 0)
        self.assertEquals(self.white._parent_index_, 1)
        self.assertEquals(self.param._parent_index_, 0)
        pass

    def test_fixes(self):
        self.white.fix(warning=False)
        self.test1.unlink_parameter(self.param)
        self.assertTrue(self.test1._has_fixes())
        self.assertListEqual(self.test1._fixes_.tolist(),[transformations.UNFIXED,transformations.UNFIXED,transformations.FIXED])
        self.test1.kern.link_parameter(self.white, 0)
        self.assertListEqual(self.test1._fixes_.tolist(),[transformations.FIXED,transformations.UNFIXED,transformations.UNFIXED])
        self.test1.kern.rbf.fix()
        self.assertListEqual(self.test1._fixes_.tolist(),[transformations.FIXED]*3)
        self.test1.fix()
        self.assertTrue(self.test1.is_fixed)
        self.assertListEqual(self.test1._fixes_.tolist(),[transformations.FIXED]*self.test1.size)

    def test_remove_parameter(self):
        self.white.fix()
        self.test1.kern.unlink_parameter(self.white)
        self.assertIs(self.test1._fixes_,None)

        self.assertIsInstance(self.white.constraints, ParameterIndexOperations)
        self.assertListEqual(self.white._fixes_.tolist(), [transformations.FIXED])
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.param.constraints._param_index_ops)

        self.test1.link_parameter(self.white, 0)
        self.assertIs(self.test1.constraints, self.white.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.param.constraints._param_index_ops)
        self.assertListEqual(self.test1.constraints[transformations.__fixed__].tolist(), [0])
        self.assertIs(self.white._fixes_,None)
        self.assertListEqual(self.test1._fixes_.tolist(),[transformations.FIXED] + [transformations.UNFIXED] * 52)

        self.test1.unlink_parameter(self.white)
        self.assertIs(self.test1._fixes_,None)
        self.assertListEqual(self.white._fixes_.tolist(), [transformations.FIXED])
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.param.constraints._param_index_ops)
        self.assertListEqual(self.test1.constraints[transformations.Logexp()].tolist(), list(range(self.param.size, self.param.size+self.rbf.size)))

    def test_remove_parameter_param_array_grad_array(self):
        val = self.test1.kern.param_array.copy()
        self.test1.kern.unlink_parameter(self.white)
        self.assertListEqual(self.test1.kern.param_array.tolist(), val[:2].tolist())

    def test_add_parameter_already_in_hirarchy(self):
        self.assertRaises(HierarchyError, self.test1.link_parameter, self.white.parameters[0])

    def test_default_constraints(self):
        self.assertIs(self.rbf.variance.constraints._param_index_ops, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertListEqual(self.rbf.constraints.indices()[0].tolist(), list(range(2)))
        kern = self.test1.kern
        self.test1.unlink_parameter(kern)
        self.assertListEqual(kern.constraints[transformations.Logexp()].tolist(), list(range(3)))

    def test_constraints(self):
        self.rbf.constrain(transformations.Square(), False)
        self.assertListEqual(self.test1.constraints[transformations.Square()].tolist(), list(range(self.param.size, self.param.size+self.rbf.size)))
        self.assertListEqual(self.test1.constraints[transformations.Logexp()].tolist(), [self.param.size+self.rbf.size])

        self.test1.kern.unlink_parameter(self.rbf)
        self.assertListEqual(self.test1.constraints[transformations.Square()].tolist(), [])

        self.test1.unconstrain_positive()
        self.assertListEqual(self.test1.constraints[transformations.Logexp()].tolist(), [])

    def test_constraints_link_unlink(self):
        self.test1.unlink_parameter(self.test1.kern)
        self.test1.kern.rbf.unlink_parameter(self.test1.kern.rbf.lengthscale)
        self.test1.kern.rbf.link_parameter(self.test1.kern.rbf.lengthscale)
        self.test1.kern.rbf.unlink_parameter(self.test1.kern.rbf.lengthscale)
        self.test1.link_parameter(self.test1.kern)

    def test_constraints_views(self):
        self.assertEqual(self.white.constraints._offset, self.param.size+self.rbf.size)
        self.assertEqual(self.rbf.constraints._offset, self.param.size)
        self.assertEqual(self.param.constraints._offset, 0)

    def test_fixing_randomize(self):
        self.white.fix(warning=True)
        val = float(self.white.variance)
        self.test1.randomize()
        self.assertEqual(val, self.white.variance)

    def test_randomize(self):
        ps = self.test1.param.view(np.ndarray).copy()
        self.test1.param[2:5].fix()
        self.test1.param.randomize()
        self.assertFalse(np.all(ps==self.test1.param),str(ps)+str(self.test1.param))

    def test_fixing_randomize_parameter_handling(self):
        self.rbf.fix(0.1, warning=True)
        val = float(self.rbf.variance)
        self.test1.kern.randomize()
        self.assertEqual(val, self.rbf.variance)

    def test_add_parameter_in_hierarchy(self):
        self.test1.kern.rbf.link_parameter(Param("NEW", np.random.rand(2), transformations.NegativeLogexp()), 1)
        self.assertListEqual(self.test1.constraints[transformations.NegativeLogexp()].tolist(), list(range(self.param.size+1, self.param.size+1 + 2)))
        self.assertListEqual(self.test1.constraints[transformations.Logistic(0,1)].tolist(), list(range(self.param.size)))
        self.assertListEqual(self.test1.constraints[transformations.Logexp(0,1)].tolist(), np.r_[50, 53:55].tolist())

    def test_checkgrad_hierarchy_error(self):
        self.assertRaises(HierarchyError, self.test1.checkgrad)
        self.assertRaises(HierarchyError, self.test1.kern.white.checkgrad)

    def test_printing(self):
        print(self.test1)
        print(self.param)
        print(self.test1[''])

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.test_add_parameter']
    unittest.main()
