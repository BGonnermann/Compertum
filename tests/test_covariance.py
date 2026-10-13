"""Independent hand examples and adversarial covariance contracts."""
import numpy as np
import pytest
from compertum.mathematics.covariance import CovarianceRefused, assess_covariance, sample_covariance, shrink_covariance


def intervals(n,p): return [[f'interval-{i}']*p for i in range(n)]


@pytest.mark.parametrize('delta,variance,eigenvalues,inverse',[(0,1,[0,2],False),(.25,.875,[.25,1.75],True),(1,.5,[1,1],True)])
def test_hand_shrinkage(delta,variance,eigenvalues,inverse):
    matrix=shrink_covariance([[1,1],[1,1]],delta)
    r=assess_covariance(matrix,[.5,.5])
    assert r.forecast==variance and r.raw_quadratic==variance and r.adjustment==0
    assert r.eigenvalues==pytest.approx(eigenvalues)
    assert (r.inversion_status=='INVERSION_ACCEPTED')==inverse
    if inverse: assert np.asarray(r.matrix)@np.asarray(r.inverse)==pytest.approx(np.eye(2))
    else: assert r.inverse is None


def test_sample_ddof_mean_and_raw_immutability():
    raw=np.array([[1.,2.],[3.,4.],[5.,6.]])
    original=raw.copy(); r=sample_covariance(raw,intervals(3,2))
    assert np.array_equal(raw,original)
    assert r.mean==(3.,4.) and r.matrix==((4.,4.),(4.,4.))
    assert r.observations==3 and r.assets==2 and r.rank==1


def test_centered_twelve_rank_eleven():
    r=sample_covariance(np.eye(12),intervals(12,12))
    assert r.rank==11
    assert np.asarray(r.matrix)==pytest.approx((np.eye(12)-np.ones((12,12))/12)/11)
    q=assess_covariance(r.matrix,[1/12]*12)
    assert q.forecast>=0 and q.forecast<1e-15
    assert q.inversion_status=='INVERSION_REJECTED'
    assert assess_covariance(shrink_covariance(r.matrix,.25),[1/12]*12).inversion_status=='INVERSION_ACCEPTED'


@pytest.mark.parametrize('delta',[0,.25,1])
def test_zero_diagonal_remains_singular(delta):
    r=assess_covariance(shrink_covariance([[1,0],[0,0]],delta),[0,1])
    assert r.forecast==0 and r.inversion_status=='INVERSION_REJECTED'


def test_nearly_collinear_is_valid_without_inverse():
    x=np.array([[1,1],[2,2+1e-12],[3,3-1e-12],[4,4]])
    r=assess_covariance(sample_covariance(x,intervals(4,2)).matrix,[.5,.5])
    assert r.forecast>0 and r.inversion_status=='INVERSION_REJECTED'


def test_algebraic_pd_does_not_mean_numeric_inversion():
    r=assess_covariance([[1,0],[0,1e-12]],[0,1])
    assert r.forecast==1e-12 and r.inversion_status=='INVERSION_REJECTED'


@pytest.mark.parametrize('small,status',[(1e-8,'INVERSION_ACCEPTED'),(9.999e-9,'INVERSION_REJECTED'),(1e-10,'INVERSION_REJECTED')])
def test_inversion_boundary(small,status):
    assert assess_covariance([[1,0],[0,small]],[1,0]).inversion_status==status


def test_tiny_negative_quadratic_records_rounding():
    r=assess_covariance([[-1e-10]],[2])
    assert r.raw_matrix==((-1e-10,),)
    assert r.raw_quadratic==-4e-10 and r.quadratic_tolerance==4e-10
    assert r.forecast==0 and r.adjustment==4e-10
    assert r.inversion_status=='INVERSION_REJECTED'
    zero=assess_covariance([[-1e-10]],[0])
    assert zero.forecast==0 and zero.quadratic_tolerance==0 and zero.adjustment==0


def test_symmetrization_preserves_raw_and_scaled_threshold():
    raw=[[1,5e-11],[0,1]];r=assess_covariance(raw,[1,1])
    assert r.raw_matrix==((1.,5e-11),(0.,1.))
    assert r.matrix==((1.,2.5e-11),(2.5e-11,1.))
    assert r.forecast==pytest.approx(2.00000000005)
    assert raw==[[1,5e-11],[0,1]]
    assert assess_covariance([[1e6,5e-5],[0,1e6]],[1,1]).forecast>0


@pytest.mark.parametrize('matrix',[
 [],[1,2],[[1,0]],[[1,2],[2,1]],[[1,1,1],[1,1,-1],[1,-1,1]],
 [[-1.0001e-10]],[[1,2e-10],[0,1]],[[float('nan')]],[[float('inf')]],
 [[True]], [['1']], [[1j]],np.eye(13),[[1e308,1e308],[1e308,1e308]],
])
def test_invalid_matrix_refused(matrix):
    with pytest.raises(CovarianceRefused): assess_covariance(matrix,[1])


@pytest.mark.parametrize('weights',[[],[1,2],[float('nan')],[float('inf')],[True],['1'],[1j],[[1]],[1e308]])
def test_invalid_weights_refused(weights):
    with pytest.raises(CovarianceRefused): assess_covariance([[1]],weights)


@pytest.mark.parametrize('delta',[-1,.5,2,float('nan'),True,'0.25'])
def test_unregistered_delta_refused(delta):
    with pytest.raises(CovarianceRefused): shrink_covariance([[1]],delta)


def test_shrinkage_requires_psd_not_only_positive_diagonal():
    with pytest.raises(CovarianceRefused,match='INDEFINITE'):shrink_covariance([[1,2],[2,1]],.25)


@pytest.mark.parametrize('raw',[[[1]],[[1],[float('nan')]],[[1],[float('inf')]],[[True],[False]],[[1j],[2j]],[[1],[2,3]],np.ones((253,1)),np.ones((2,13)),[[1e308],[-1e308]]])
def test_invalid_return_rows_refused(raw):
    with pytest.raises(CovarianceRefused):sample_covariance(raw,intervals(len(raw),1))


@pytest.mark.parametrize('ids',[[['a'],['a']],[['a','b'],['c','c']],[['a','a']],[['',''],['b','b']],[[None,None],['b','b']]])
def test_missing_asynchronous_duplicate_intervals_refused(ids):
    with pytest.raises(CovarianceRefused):sample_covariance([[1,2],[3,4]],ids)


def test_eigensolver_failure_is_refusal(monkeypatch):
    def fail(*a,**k):raise np.linalg.LinAlgError('controlled failure')
    monkeypatch.setattr(np.linalg,'eigvalsh',fail)
    with pytest.raises(CovarianceRefused):assess_covariance([[1]],[1])


def test_inverse_failure_does_not_erase_forecast(monkeypatch):
    def fail(*a,**k):raise np.linalg.LinAlgError('controlled failure')
    monkeypatch.setattr(np.linalg,'inv',fail)
    r=assess_covariance([[1]],[1])
    assert r.forecast==1 and r.inversion_status=='INVERSION_REJECTED' and r.inverse is None

@pytest.mark.parametrize('target',['returns','matrix','weights'])
def test_masked_missing_numeric_input_is_not_silently_filled(target):
    with pytest.raises(CovarianceRefused,match='MASKED'):
        if target=='returns':sample_covariance(np.ma.array([[1.,2.],[3.,4.]],mask=[[False,True],[False,False]]),intervals(2,2))
        elif target=='matrix':assess_covariance(np.ma.array([[1.,0.],[0.,1.]],mask=[[True,False],[False,False]]),[1,0])
        else:assess_covariance([[1.]],np.ma.array([1.],mask=[True]))


def test_large_offset_does_not_create_a_false_invertible_covariance():
    raw=np.full((12,12),1e16)+2*np.eye(12)
    r=sample_covariance(raw,intervals(12,12))
    expected=(4/11)*(np.eye(12)-np.ones((12,12))/12)
    assert r.matrix==pytest.approx(expected,rel=1e-13,abs=1e-15)
    assert r.rank==11
    assert assess_covariance(r.matrix,[1/12]*12).inversion_status=='INVERSION_REJECTED'

@pytest.mark.parametrize('matrix,expected',[([[-1e-10]],1),([[-1e-10,0],[0,-.5e-10]],2),([[1,0],[0,-1e-10]],1e10)])
def test_condition_uses_singular_values_even_for_permitted_negative_roundoff(matrix,expected):
    r=assess_covariance(matrix,[0]*len(matrix))
    assert r.condition_number==expected
    assert r.inversion_status=='INVERSION_REJECTED'

@pytest.mark.parametrize('target',['returns','matrix'])
def test_nested_masked_rows_are_not_silently_filled(target):
    rows=[np.ma.array([1.,2.],mask=[False,True]),np.array([3.,4.])]
    with pytest.raises(CovarianceRefused,match='MASKED'):
        if target=='returns':sample_covariance(rows,intervals(2,2))
        else:assess_covariance(rows,[1,0])
