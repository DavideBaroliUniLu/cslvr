from fenics               import *
from dolfin_adjoint       import *
from cslvr.inputoutput    import print_text, get_text, print_min_max
from copy                 import copy
from scipy.io             import savemat
from ufl                  import indexed
import numpy              as np
import matplotlib.pyplot  as plt
import matplotlib         as mpl
import sys
import os
import re


class Model(object):
  """ 
  The basic model from which each of these inherit :

   * :class:`~latmodel.LatModel`       - plane strain model
   * :class:`~d1model.D1Model`         - 1D firn model
   * :class:`~d2model.D2Model`         - 2D model (SSA, SIA, balance velocity)
   * :class:`~d3model.D3Model`         - 3D model (first-order, full-Stokes)

  :param mesh:         the finite-element mesh
  :param out_dir:      location for the output directory
  :param order:        order of the shape function basis, default linear
  :param use_periodic: use periodic boundaries or not
  :type mesh:          :class:`~fenics.Mesh`
  :type out_dir:       string
  :type order:         int
  :type use_periodic:  bool
  """
  
  def __init__(self, mesh, out_dir='./results/', order=1,
               use_periodic=False, **kwargs):
    """
    Create and instance of the model.
    """
    self.this = super(type(self), self)  # pointer to this base class
  
    s = "::: INITIALIZING BASE MODEL :::"
    print_text(s, cls=self.this)
    
    parameters['form_compiler']['quadrature_degree']  = order + 1
    parameters["std_out_all_processes"]               = False
    parameters['form_compiler']['optimize']           = True
    parameters['form_compiler']['cpp_optimize']       = True
    parameters['form_compiler']['cpp_optimize_flags'] = "-O3"
    parameters["form_compiler"]["representation"]     = 'uflacs'
    parameters['plotting_backend']                    = 'matplotlib'

    PETScOptions.set("mat_mumps_icntl_14", 100.0)

    self.order        = order
    self.out_dir      = out_dir
    self.MPI_rank     = MPI.rank(mpi_comm_world())
    self.use_periodic = use_periodic
    
    self.generate_constants()
    self.set_mesh(mesh)
    self.generate_function_spaces(**kwargs)
    self.initialize_variables()

  def color(self):
    """
    The color used for printing messages to the screen.

    :rtype: string
    """
    return '148'

  def generate_constants(self):
    """
    Initializes important constants, including :
    
    +------------------+---------------+----------------------------------+ 
    | name of constant | value         | description                      |
    +==================+===============+==================================+
    | ``self.kcLw``    | 9.2e-9        | creep coefficient low            |
    +------------------+---------------+----------------------------------+ 
    | ``self.kg``      | 1.3e-7        | grain growth coefficient         |
    +------------------+---------------+----------------------------------+ 
    | ``self.Ec``      | 6e4           | act. energy for water in ice     |
    +------------------+---------------+----------------------------------+ 
    | ``self.Eg``      | 42.4e3        | act. energy for grain growth     |
    +------------------+---------------+----------------------------------+ 
    | ``self.etaw``    | 1.787e-3      | viscosity of water at Tw         |
    +------------------+---------------+----------------------------------+ 
    | ``self.eps_reg`` | 1e-15         | strain-rate reg. parameter       |
    +------------------+---------------+----------------------------------+ 
    | ``self.n``       | 3.0           | Glen's flow exponent             |
    +------------------+---------------+----------------------------------+ 
    | ``self.spy``     | 31556926.0    | seconds per year                 |
    +------------------+---------------+----------------------------------+ 
    | ``self.rhoi``    | 910.0         | ice density                      |
    +------------------+---------------+----------------------------------+ 
    | ``self.rhow``    | 1000.0        | water density                    |
    +------------------+---------------+----------------------------------+ 
    | ``self.rhosw``   | 1028.0        | sea-water density                |
    +------------------+---------------+----------------------------------+ 
    | ``self.rhom``    | 550.0         | firn pore-close-off density      |
    +------------------+---------------+----------------------------------+ 
    | ``self.rhoc``    | 815.0         | firn density critical value      |
    +------------------+---------------+----------------------------------+ 
    | ``self.g``       | 9.80665       | gravitational acceleration       |
    +------------------+---------------+----------------------------------+ 
    | ``self.a0``      | 5.45e10       | ice hardness limit               |
    +------------------+---------------+----------------------------------+ 
    | ``self.Q0``      | 13.9e4        | ice activation energy            |
    +------------------+---------------+----------------------------------+ 
    | ``self.R``       | 8.3144621     | universal gas constant           |
    +------------------+---------------+----------------------------------+ 
    | ``self.ki``      | 2.1           | thermal conductivity of ice      |
    +------------------+---------------+----------------------------------+ 
    | ``self.kw``      | 0.561         | thermal conductivity of water    |
    +------------------+---------------+----------------------------------+ 
    | ``self.ci``      | 2009.0        | heat capacity of ice             |
    +------------------+---------------+----------------------------------+ 
    | ``self.cw``      | 4217.6        | Heat capacity of water at Tw     |
    +------------------+---------------+----------------------------------+ 
    | ``self.L``       | 3.3355e5      | latent heat of ice               |
    +------------------+---------------+----------------------------------+ 
    | ``self.ghf``     | 0.042 * spy   | geothermal heat flux             |
    +------------------+---------------+----------------------------------+ 
    | ``self.gamma``   | 9.8e-8        | pressure melt. p't depth dep.    |
    +------------------+---------------+----------------------------------+ 
    | ``self.nu``      | 3.5e3         | moisture diffusivity             |
    +------------------+---------------+----------------------------------+ 
    | ``self.T_w``     | 273.15        | Triple point of water            |
    +------------------+---------------+----------------------------------+ 
    | ``self.a_T_l``   | 3.985e-13*spy | lower bound of flow-rate const.  |
    +------------------+---------------+----------------------------------+ 
    | ``self.a_T_u``   | 1.916e3*spy   | upper bound of flow-rate const.  |
    +------------------+---------------+----------------------------------+ 
    | ``self.Q_T_l``   | 6e4           | lower bound of ice act. energy   |
    +------------------+---------------+----------------------------------+ 
    | ``self.Q_T_u``   | 13.9e4        | upper bound of ice act. energy   |
    +------------------+---------------+----------------------------------+ 
    """
    s = "::: generating constants :::"
    print_text(s, cls=self.this)

    spy = 31556926.0
    ghf = 0.042 * spy  # W/m^2 = J/(s*m^2) = spy * J/(a*m^2)

    # Constants :
    self.kcHh    = Constant(3.7e-9)
    self.kcHh.rename('kcHh', 'creep coefficient high')

    self.kcLw    = Constant(9.2e-9)
    self.kcLw.rename('kcLw', 'creep coefficient low ')

    self.kg      = Constant(1.3e-7)
    self.kg.rename('kg', 'grain growth coefficient')

    self.Ec      = Constant(6e4)
    self.Ec.rename('Ec', 'act. energy for water in ice')

    self.Eg      = Constant(42.4e3)
    self.Eg.rename('Eg', 'act. energy for grain growth')

    self.etaw    = Constant(1.787e-3)
    self.etaw.rename('etaw', 'Dynamic viscosity of water at Tw')

    self.eps_reg = Constant(1e-15)
    self.eps_reg.rename('eps_reg', 'strain rate regularization parameter')

    self.n       = Constant(3.0)
    self.n.rename('n', "Glen's flow exponent")

    self.spy     = Constant(spy)
    self.spy.rename('spy', 'seconds per year')

    self.rhoi    = Constant(910.0)
    self.rhoi.rename('rhoi', 'ice density')

    self.rhow    = Constant(1000.0)
    self.rhow.rename('rhow', 'water density')

    self.rhosw   = Constant(1028.0)
    self.rhosw.rename('rhosw', 'sea-water density')
    
    self.rhom    = Constant(550.0)
    self.rhom.rename('rhom', 'firn pore close-off density')

    self.rhoc    = Constant(815.0)
    self.rhoc.rename('rhoc', 'firn density critical value')

    self.g       = Constant(9.80665)
    self.g.rename('g', 'gravitational acceleration')

    self.a0      = Constant(5.45e10)
    self.a0.rename('a0', 'ice hardness limit')

    self.Q0      = Constant(13.9e4)
    self.Q0.rename('Q0', 'ice activation energy')

    self.R       = Constant(8.3144621)
    self.R.rename('R', 'universal gas constant')

    self.ki      = Constant(2.1)
    self.ki.rename('ki', 'thermal conductivity of ice')

    self.kw      = Constant(0.561)
    self.kw.rename('kw', 'thermal conductivity of water')

    self.ci      = Constant(2009.0)
    self.ci.rename('ci', 'heat capacity of ice')
    
    self.cw      = Constant(4217.6)
    self.cw.rename('cw', 'Heat capacity of water at Tw')

    self.L       = Constant(3.3355e5)
    self.L.rename('L', 'latent heat of ice')

    self.ghf     = Constant(ghf)
    self.ghf.rename('ghf', 'geothermal heat flux')

    self.gamma   = Constant(9.8e-8)
    self.gamma.rename('gamma', 'pressure melting point depth dependence')

    self.nu      = Constant(3.5e3)
    self.nu.rename('nu', 'moisture diffusivity')

    self.T_w     = Constant(273.15)
    self.T_w.rename('T_w', 'Triple point of water')

    self.a_T_l   = Constant(3.985e-13*spy)
    self.a_T_l.rename('a_T_l', 'lower bound of flow-rate constant')

    self.a_T_u   = Constant(1.916e3*spy)
    self.a_T_u.rename('a_T_u', 'upper bound of flow-rate constant')

    self.Q_T_l   = Constant(6e4)
    self.Q_T_l.rename('Q_T_l', 'lower bound of ice activation energy')

    self.Q_T_u   = Constant(13.9e4)
    self.Q_T_u.rename('Q_T_u', 'upper bound of ice activation energy')
  
  def set_subdomains(self, f):
    """
    Set the facet subdomains FacetFunction self.ff, cell subdomains
    CellFunction self.cf, and accumulation FacetFunction self.ff_acc from
    MeshFunctions saved in an .h5 file <f>.
    """
    s = "::: setting subdomains :::"
    print_text(s, cls=self)

    self.ff     = MeshFunction('size_t', self.mesh)
    self.cf     = MeshFunction('size_t', self.mesh)
    self.ff_acc = MeshFunction('size_t', self.mesh)
    f.read(self.ff,     'ff')
    f.read(self.cf,     'cf')
    f.read(self.ff_acc, 'ff_acc')
    
    self.set_measures()

  def generate_pbc(self):
    """
    return a :class:`fenics.SubDomain` of periodic lateral boundaries.
    """
    raiseNotDefined()
    
  def set_mesh(self, f):
    """
    Sets the ``mesh`` instance to ``f``, either a :class:`fenics.Mesh` or  ``.h5``
    file with a mesh saved with name ``mesh``.
    """
    s = "::: setting mesh :::"
    print_text(s, cls=self.this)

    if isinstance(f, dolfin.cpp.io.HDF5File):
      self.mesh = Mesh()
      f.read(self.mesh, 'mesh', False)

    elif isinstance(f, dolfin.cpp.mesh.Mesh):
      self.mesh = f

    self.dim   = self.mesh.ufl_cell().topological_dimension()

  def calculate_boundaries(self):
    """
    Determines the boundaries of the current ``self.mesh``.
  
    External boundaries :

    * ``self.GAMMA_S_GND`` -- grounded upper surface
    * ``self.GAMMA_B_GND`` -- grounded lower surface (bedrock)
    * ``self.GAMMA_S_FLT`` -- shelf upper surface
    * ``self.GAMMA_B_FLT`` -- shelf lower surface
    * ``self.GAMMA_L_DVD`` -- basin divides
    * ``self.GAMMA_L_OVR`` -- terminus over water
    * ``self.GAMMA_L_UDR`` -- terminus under water
    * ``self.GAMMA_U_GND`` -- grounded upper surface with :math:`\mathbf{u}_{ob}`
    * ``self.GAMMA_U_FLT`` -- shelf upper surface with :math:`\mathbf{u}_{ob}`
    
    Internal boundaries :

    * ``self.OMEGA_GND``   -- internal cells located over bedrock
    * ``self.OMEGA_FLT``   -- internal cells located over water

    These are then used to define the measures used for integration by FEniCS
    by calling :func:`set_measures`.
    """
    raiseNotDefined()

  def set_measures(self):
    """
    set the new measure space for facets ``self.ds`` and cells ``self.dx`` for
    the boundaries marked by FacetFunction ``self.ff`` and CellFunction 
    ``self.cf``, respectively.

    Also, the number of facets marked by 
    :func:`calculate_boundaries` :

    * ``self.N_OMEGA_GND``   -- number of cells marked ``self.OMEGA_GND``  
    * ``self.N_OMEGA_FLT``   -- number of cells marked ``self.OMEGA_FLT``  
    * ``self.N_GAMMA_S_GND`` -- number of facets marked ``self.GAMMA_S_GND``
    * ``self.N_GAMMA_B_GND`` -- number of facets marked ``self.GAMMA_B_GND``
    * ``self.N_GAMMA_S_FLT`` -- number of facets marked ``self.GAMMA_S_FLT``
    * ``self.N_GAMMA_B_FLT`` -- number of facets marked ``self.GAMMA_B_FLT``
    * ``self.N_GAMMA_L_DVD`` -- number of facets marked ``self.GAMMA_L_DVD``
    * ``self.N_GAMMA_L_OVR`` -- number of facets marked ``self.GAMMA_L_OVR``
    * ``self.N_GAMMA_L_UDR`` -- number of facets marked ``self.GAMMA_L_UDR``
    * ``self.N_GAMMA_U_GND`` -- number of facets marked ``self.GAMMA_U_GND``
    * ``self.N_GAMMA_U_FLT`` -- number of facets marked ``self.GAMMA_U_FLT``

    The subdomains corresponding to FacetFunction ``self.ff`` are :

    * ``self.dBed_g``  --  grounded bed
    * ``self.dBed_f``  --  floating bed
    * ``self.dBed``    --  bed
    * ``self.dSrf_gu`` --  grounded with U observations
    * ``self.dSrf_fu`` --  floating with U observations
    * ``self.dSrf_u``  --  surface with U observations
    * ``self.dSrf_g``  --  surface of grounded ice
    * ``self.dSrf_f``  --  surface of floating ice
    * ``self.dSrf``    --  surface
    * ``self.dLat_d``  --  lateral divide
    * ``self.dLat_to`` --  lateral terminus overwater
    * ``self.dLat_tu`` --  lateral terminus underwater
    * ``self.dLat_t``  --  lateral terminus
    * ``self.dLat``    --  lateral

    The subdomains corresponding to CellFunction ``self.cf`` are :

    * ``self.dx_g``    --  internal above grounded
    * ``self.dx_f``    --  internal above floating
    """
    raiseNotDefined()
  
  def set_out_dir(self, out_dir):
    """
    Set the output directory to string ``out_dir``.

    :param out_dir: the output directory for any output generated by 
                    :func:`save_hdf5`, :func:`save_xdmf`, :func:`save_pvd`,
                    :func:`save_list_to_hdf5`, :func:`save_subdomain_data`,
                    and :func:`save_mesh`.
    :type out_dir:  string
    """
    self.out_dir = out_dir
    s = "::: output directory changed to '%s' :::" % out_dir
    print_text(s, cls=self.this)

  def generate_function_spaces(self):
    r"""
    Generates the finite-element function spaces used by all children of this
    :class:`Model`.

    The element shape-functions available from this method are :

    * ``self.Q``  -- :math:`\mathcal{H}^k(\Omega)`
    * ``self.Q2`` -- :math:`\mathcal{H}^k(\Omega) \times \mathcal{H}^k(\Omega)`
    * ``self.Q3`` -- :math:`\mathcal{H}^k(\Omega) \times \mathcal{H}^k(\Omega) \times \mathcal{H}^k(\Omega)`
    * ``self.Q4`` -- :math:`\mathcal{H}^k(\Omega) \times \mathcal{H}^k(\Omega) \times \mathcal{H}^k(\Omega) \times \mathcal{H}^k(\Omega)`  
    * ``self.Q_non_periodic`` -- same as ``self.Q``, but without periodic constraints
    * ``self.Q3_non_periodic`` -- same as ``self.Q3``, but without periodic constraints
    * ``self.V`` -- same as ``self.Q3`` but formed using :class:`~fenics.VectorFunctionSpace`

    """
    order = self.order

    s = "::: generating fundamental function spaces of order %i :::" % order
    print_text(s, cls=self.this)
    
    # define elements that may or may not be used :
    self.Q1e    = FiniteElement("CG", self.mesh.ufl_cell(), order)
    self.V1e    = VectorElement("CG", self.mesh.ufl_cell(), order)
    self.Q2e    = FiniteElement("CG", self.mesh.ufl_cell(), order+1)
    self.QM2e   = MixedElement([self.Q1e]*2)
    self.QM3e   = MixedElement([self.Q1e]*3)
    self.QM4e   = MixedElement([self.Q1e]*4)
    self.QTH3e  = MixedElement([self.Q2e,self.Q2e,self.Q2e,self.Q1e])
    self.BDMe   = FiniteElement("BDM", self.mesh.ufl_cell(), 1)
    self.DGe    = FiniteElement("DG",  self.mesh.ufl_cell(), 0)
    self.DG1e   = FiniteElement("DG",  self.mesh.ufl_cell(), 1)
    self.QTH2e  = MixedElement([self.Q2e,self.Q2e,self.Q1e])
    self.BDMMe  = MixedElement([self.BDMe, self.DGe])

    # NOTE: generate periodic function spaces if required
    # the functionspaces must be initialized with constrained domains prior
    # to mesh deformation.  If periodic boundary conditions are not used, the 
    # individual "Physics" classes will initialize the FunctionSpaces to 
    # conserve CPU time and especially memory :
    if self.use_periodic:
      self.generate_pbc()
      self.Q                = FunctionSpace(self.mesh, self.Q1e,
                                            constrained_domain=self.pBC)
      self.Q2               = FunctionSpace(self.mesh, self.QM2e,
                                            constrained_domain=self.pBC)
      self.Q3               = FunctionSpace(self.mesh, self.QM3e,
                                            constrained_domain=self.pBC)
      self.Q_non_periodic   = FunctionSpace(self.mesh, self.Q1e)
      self.Q3_non_periodic  = FunctionSpace(self.mesh, self.QM3e)
    else:
      self.pBC = None
      self.Q                = FunctionSpace(self.mesh, self.Q1e)
      self.Q3               = FunctionSpace(self.mesh, self.QM3e)
      self.Q_non_periodic   = self.Q
      self.Q3_non_periodic  = self.Q3

    # NOTE: the function spaces "_non_periodic" are needed as some 
    # functions must be defined as non-periodic for the solution to make sense 
    # see (self.initialize_variables()).
    
    self.V  = FunctionSpace(self.mesh, self.V1e)

    s = "    - fundamental function spaces created - "
    print_text(s, cls=self.this)
  
  def init_S(self, S):
    r"""
    Set surface topography :math:`S`, ``self.S``,
    by calling :func:`assign_variable`.
    
    :param S:   surface topography
    """
    s = "::: initializng surface topography :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.S, S)

  def init_B(self, B):
    r"""
    Set basal topography :math:`B`, ``self.B``,
    by calling :func:`assign_variable`.
    
    :param B:   basal topography
    """
    s = "::: initializng basal topography :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.B, B)

  def init_B_err(self, B_err):
    r"""
    Set basal topography uncertainty :math:`B_{\epsilon}`, ``self.B_err``,
    by calling :func:`assign_variable`.
    
    :param B_err:   basal topography uncertainty
    """
    s = "::: initializng basal topography uncertainty :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.B_err, B_err)
  
  def init_p(self, p):
    r"""
    Set pressure :math:`p`, ``self.p``,
    by calling :func:`assign_variable`.
    
    :param p:   pressure
    """
    s = "::: initializing pressure :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.p, p)
  
  def init_theta(self, theta):
    r"""
    Set internal energy :math:`\theta`, ``self.theta``,
    by calling :func:`assign_variable`.
    
    :param theta:   internal energy
    """
    s = "::: initializing internal energy :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.theta, theta)
    # init pressure-melting temperature thing :
    theta_v = self.theta.vector().array()
    T_v     = (-146.3 + np.sqrt(146.3**2 + 2*7.253*theta_v)) / 7.253
    T_v[T_v > self.T_w(0)] = self.T_w(0)
    self.init_Tp(T_v)
  
  def init_theta_app(self, theta_app):
    r"""
    Set the internal energy approximation :math:`\theta_{app}`,
    ``self.theta_app``,
    by calling :func:`assign_variable`.
    
    :param theta_app:   internal energy approximation
    """
    s = "::: initializing internal energy approximation :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.theta_app, theta_app)
  
  def init_theta_surface(self, theta_surface):
    r"""
    Set the surface internal energy :math:`\theta_S`, ``self.theta_surface``,
    by calling :func:`assign_variable`.
    
    :param theta_surface:   surface internal energy
    """
    s = "::: initializing surface energy :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.theta_surface, theta_surface)
  
  def init_theta_float(self, theta_float):
    r"""
    Set the floating ice internal energy :math:`\theta_{sea}`,
    ``self.theta_float``, by calling :func:`assign_variable`.
    
    :param theta_float:   internal energy in contact with water
    """
    s = "::: initializing internal energy of facets in contact with water :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.theta_float, theta_float)
  
  def init_T(self, T):
    r"""
    Set temperature :math:`T`, ``self.T``,
    by calling :func:`assign_variable`.
    
    :param T: temperature 
    """
    s = "::: initializing absolute temperature :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.T, T)
  
  def init_Tp(self, Tp):
    r"""
    Set pressure-adjusted temperature :math:`T_p = T + \gamma p`, ``self.Tp``,
    by calling :func:`assign_variable`.
    
    :param Tp:   pressure-adjusted temperature :math:`T_p = T + \gamma p`
    """
    s = "::: initializing pressure-adjusted temperature :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Tp, Tp)
  
  def init_W(self, W):
    r"""
    Set water content :math:`W`, ``self.W``,
    by calling :func:`assign_variable`.
    
    :param W:  water content 
    """
    s = "::: initializing water content :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.W, W)
  
  def init_Wc(self, Wc):
    r"""
    Set maximum observed water content :math:`W_c`, ``self.Wc``,
    by calling :func:`assign_variable`.
    
    :param Wc:   maximum allowed water content
    """
    s = "::: initializing maximum water content :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Wc, Wc)
  
  def init_Mb(self, Mb):
    r"""
    Set basal melting rate :math:`M_b`, ``self.Mb``,
    by calling :func:`assign_variable`.
    
    :param Mb:   basal-melt rate
    """
    s = "::: initializing basal-melt rate :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Mb, Mb)
  
  def init_adot(self, adot):
    r"""
    Set accumulation/ablation :math:`\dot{a}`, ``self.adot``,
    by calling :func:`assign_variable`.
    
    :param adot:   accumulation/ablation :math:`\dot{a}`
    """
    s = "::: initializing accumulation/ablation function :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.adot, adot)
  
  def init_beta(self, beta):
    r"""
    Set basal traction :math:`\beta`, ``self.beta``,
    by calling :func:`assign_variable`.
    
    :param beta:  basal traction :math:`\beta`
    """
    s = "::: initializing basal traction coefficient :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.beta, beta)
  
  def init_lam(self, lam):
    r"""
    Set basal normal stress magnitude :math:`\underline{n} \cdot \underline{\underline{\sigma}} \cdot \underline{n}`, ``self.lam``,
    by calling :func:`assign_variable`.
    
    :param lam:  basal normal stress magnitude :math:`\underline{n} \cdot \underline{\underline{\sigma}} \cdot \underline{n}`
    """
    s = "::: initializing basal traction coefficient :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.lam, lam)
  
  def init_A(self, A):
    r"""
    Set flow-rate factor :math:`A`, ``self.A``,
    by calling :func:`assign_variable`.
    
    :param A:  flow-rate factor
    """
    s = "::: initializing flow-rate factor over grounded and shelves :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.A, A)
    
  def init_E(self, E):
    r"""
    Set flow-enhancement factor :math:`E`, ``self.E``,
    by calling :func:`assign_variable`.
    
    :param E:  enhancement factor 
    """
    s = "::: initializing enhancement factor over grounded and shelves :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.E, E)
  
  def init_eta(self, eta):
    r"""
    Set viscosity :math:`\eta`, ``self.eta``,
    by calling :func:`assign_variable`.
    
    :param eta:   viscosity
    """
    s = "::: initializing viscosity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.eta, eta)
  
  def init_etabar(self, etabar):
    r"""
    Set vertically averaged viscosity :math:`\bar{\eta}`, ``self.etabar``,
    by calling :func:`assign_variable`.
    
    :param etabar:   vertically-averaged viscosity
    """
    s = "::: initializing vertically averaged viscosity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.etabar, etabar)
  
  def init_ubar(self, ubar):
    r"""
    Set vertically averaged x-component of velocity :math:`\bar{u}`, 
    ``self.ubar``,
    by calling :func:`assign_variable`.
    
    :param ubar:   vertically-averaged x-component of velocity
    """
    s = "::: initializing vertically averaged x-component of velocity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.ubar, ubar)
  
  def init_vbar(self, vbar):
    r"""
    Set vertically averaged y-component of velocity :math:`\bar{v}`,
    ``self.vbar``,
    by calling :func:`assign_variable`.
    
    :param vbar:   vertically-averaged y-component of velocity
    """
    s = "::: initializing vertically averaged y-component of velocity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.vbar, vbar)
    
  def init_wbar(self, wbar):
    r"""
    Set vertically averaged z-component of velocity :math:`\bar{w}`,
    ``self.wbar``,
    by calling :func:`assign_variable`.
    
    :param wbar:   vertically-averaged z-component of velocity
    """
    s = "::: initializing vertically averaged z-component of velocity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.wbar, wbar)
  
  def init_T_surface(self, T_surface):
    r"""
    Set surface temperature :math:`T_S`, ``self.T_surface``,
    by calling :func:`assign_variable`.
    
    :param T_surface:   surface temperature
    """
    s = "::: initializing surface temperature :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.T_surface, T_surface)
  
  def init_q_geo(self, q_geo):
    r"""
    Set geothermal heat flux :math:`q_{geo}`, ``self.q_geo``,
    by calling :func:`assign_variable`.
    
    :param q_geo:   geothermal heat flux
    """
    s = "::: initializing geothermal heat flux :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.q_geo, q_geo)
  
  def init_q_fric(self, q_fric):
    r"""
    Set traction heat flux :math:`q_{fric}`, ``self.q_fric``,
    by calling :func:`assign_variable`.
    
    :param q_fric:  friction heat flux 
    """
    s = "::: initializing basal friction heat flux :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.q_fric, q_fric)
  
  def init_gradT_B(self, gradT_B):
    r"""
    Set basal temperature gradient 
    :math:`\left( k \nabla T \right) \cdot \mathbf{n}`, ``self.gradT_B``,
    by calling :func:`assign_variable`.
    
    :param gradT_B:   basal temperature gradient
    """
    s = "::: initializing basal temperature flux :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.gradT_B, gradT_B)
  
  def init_gradTm_B(self, gradTm_B):
    r"""
    Set basal temperature melting gradient 
    :math:`\left( k \nabla T_m \right) \cdot \mathbf{n}`, ``self.gradTm_B``,
    by calling :func:`assign_variable`.
    
    :param gradTm_B:   basal temperature melting gradient
    """
    s = "::: initializing basal temperature-melting flux :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.gradTm_B, gradTm_B)
  
  def init_u(self, u):
    r"""
    Set x-component of velocity :math:`u`, ``self.u``,
    by calling :func:`assign_variable`.
    
    :param u:  x-component of velocity
    """
    s = "::: initializing x-component of velocity :::"
    print_text(s, cls=self.this)
    u_t = Function(self.Q_non_periodic, name='u_t')
    self.assign_variable(u_t, u)
    self.assx.assign(self.u, u_t, annotate=False)
  
  def init_v(self, v):
    r"""
    Set y-component of velocity :math:`v`, ``self.v``,
    by calling :func:`assign_variable`.
    
    :param v:  y-component of velocity
    """
    s = "::: initializing y-component of velocity :::"
    print_text(s, cls=self.this)
    v_t = Function(self.Q_non_periodic, name='v_t')
    self.assign_variable(v_t, v)
    self.assy.assign(self.v, v_t, annotate=False)
  
  def init_w(self, w):
    r"""
    Set z-component of velocity :math:`w`, ``self.w``,
    by calling :func:`assign_variable`.
    
    :param w:  z-component of velocity
    """
    s = "::: initializing z-component of velocity :::"
    print_text(s, cls=self.this)
    w_t = Function(self.Q_non_periodic, name='w_t')
    self.assign_variable(w_t, w)
    self.assz.assign(self.w, w_t, annotate=False)

  def init_U(self, U):
    r"""
    Set velocity vector :math:`\mathbf{u}`, ``self.U3``,
    by calling :func:`assign_variable`.
    
    :param U: velocity vector
    """
    s = "::: initializing velocity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.U3, U)
    self.init_U_mag(self.U3)

  def init_U_mag(self, U):
    r"""
    Set velocity vector magnitude :math:`\Vert \mathbf{u} \Vert`,
    ``self.U_mag``,
    by calling :func:`assign_variable`.
    
    :param U:   velocity vector
    """
    s = "::: initializing velocity magnitude :::"
    print_text(s, cls=self.this)
    # fenics issue #405 bug workaround :
    if self.use_periodic:
      u      = Function(self.Q)
      v      = Function(self.Q)
      w      = Function(self.Q)
      assign(u, U.sub(0))
      assign(v, U.sub(1))
      assign(w, U.sub(2))
    else:
      u,v,w  = U.split(True)
    u_v      = u.vector().array()
    v_v      = v.vector().array()
    w_v      = w.vector().array()
    U_mag_v  = np.sqrt(u_v**2 + v_v**2 + w_v**2 + DOLFIN_EPS)
    self.assign_variable(self.U_mag, U_mag_v)
  
  def init_U_ob(self, u_ob, v_ob):
    r"""
    Set horizontal velocity observation vector :math:`\mathbf{u}_{ob}`,
    ``self.U_ob``, and horizontal components :math:`u_{ob}` and :math:`v_{ob}`, 
    ``self.u_ob`` and ``self.v_ob``, respectively,
    by calling :func:`assign_variable`.
    
    :param u_ob: x-component of observed velocity
    :param v_ob: y-component of observed velocity
    """
    s = "::: initializing surface velocity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.u_ob, u_ob)
    self.assign_variable(self.v_ob, v_ob)
    u_v      = self.u_ob.vector().array()
    v_v      = self.v_ob.vector().array()
    U_mag_v  = np.sqrt(u_v**2 + v_v**2 + 1e-16)
    self.assign_variable(self.U_ob, U_mag_v)
  
  def init_Ubar(self, Ubar):
    r"""
    Set balance velocity :math:`\Vert \bar{\mathbf{u}} \Vert = \bar{u}`,
    ``self.Ubar``,
    by calling :func:`assign_variable`.
    
    :param Ubar:  balance velocity magnitude 
    """
    s = "::: initializing balance velocity magnitude :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Ubar, Ubar)
  
  def init_uhat(self, uhat):
    r"""
    Set normalized x-component of lateral velocity 
    :math:`\hat{u}`, ``self.uhat``,
    by calling :func:`assign_variable`.
    
    :param uhat:   normalized x-component of velocity
    """
    s = "::: initializing normalized x-component of velocity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.uhat, uhat)
  
  def init_vhat(self, vhat):
    r"""
    Set normalized y-component of lateral velocity 
    :math:`\hat{v}`, ``self.vhat``,
    by calling :func:`assign_variable`.
    
    :param vhat:   normalized y-component of velocity
    """
    s = "::: initializing normalized y-component of velocity :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.vhat, vhat)
  
  def init_u_lat(self, u_lat):
    r"""
    Set x-component of lateral velocity :math:`u_{g_D}`, ``self.u_lat``,
    by calling :func:`assign_variable`.
    
    :param u_lat:   x-component of velocity essential condition
    """
    s = "::: initializing u lateral boundary condition :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.u_lat, u_lat)
  
  def init_v_lat(self, v_lat):
    r"""
    Set y-component of lateral velocity :math:`v_{g_D}`, ``self.v_lat``,
    by calling :func:`assign_variable`.
    
    :param v_lat:   y-component of velocity essential condition
    """
    s = "::: initializing v lateral boundary condition :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.v_lat, v_lat)
  
  def init_w_lat(self, w_lat):
    r"""
    Set z-component of lateral velocity :math:`w_{g_D}`, ``self.w_lat``,
    by calling :func:`assign_variable`.
    
    :param w_lat:   w-component of velocity essential condition
    """
    s = "::: initializing w lateral boundary condition :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.w_lat, w_lat)
  
  def init_mask(self, mask):
    r"""
    Set shelf mask ``self.mask``
    by calling :func:`assign_variable`.

    This in turn generates a vector of indices corresponding with grounded 
    and shelf vertices:

    * ``self.shf_dofs`` -- shelf dofs 
    * ``self.gnd_dofs`` -- grounded dofs
    
    :param mask:   ice-shelf mask (1 is grounded, 2 is floating)
    """
    s = "::: initializing shelf mask :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.mask, mask)
    self.shf_dofs = np.where(self.mask.vector().array() == 2.0)[0]
    self.gnd_dofs = np.where(self.mask.vector().array() == 1.0)[0]
  
  def init_U_mask(self, U_mask):
    r"""
    Set velocity observation mask ``self.U_mask``
    by calling :func:`assign_variable`.

    This in turn generates a vector of indices corresponding with grounded 
    and shelf vertices:

    * ``self.Uob_dofs`` --  observations :math:`\mathbf{u}_{ob}` present dofs 
    * ``self.Uob_missing_dofs`` -- observations :math:`\mathbf{u}_{ob}` missing dofs
    
    :param U_mask:   surface-velocity-oberservations mask (1 has observations, 0 does not)
    """
    s = "::: initializing velocity mask :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.U_mask, U_mask)
    self.Uob_dofs         = np.where(self.U_mask.vector().array() == 1.0)[0]
    self.Uob_missing_dofs = np.where(self.U_mask.vector().array() == 0.0)[0]
  
  def init_lat_mask(self, lat_mask):
    r"""
    Set lateral boundary mask ``self.lat_mask``
    by calling :func:`assign_variable`.
    
    :param lat_mask: lateral boundary mask (1 on lateral boundary, 0 not)
    """
    s = "::: initializing lateral boundary mask :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.lat_mask, lat_mask)
  
  def init_d_x(self, d_x):
    r"""
    Set x-component of flow-direction :math:`d_x`, ``self.d_x``,
    by calling :func:`assign_variable`.
    
    :param d_x:   x-component of flow direction
    """
    s = "::: initializing x-component flow direction :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.d_x, d_x)
  
  def init_d_y(self, d_y):
    r"""
    Set y-component of flow-direction :math:`d_y`, ``self.d_y``,
    by calling :func:`assign_variable`.
    
    :param d_y:   y-component of flow direction
    """
    s = "::: initializing y-component of flow direction :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.d_y, d_y)
  
  def init_time_step(self, dt):
    r"""
    Set time step :math:`\Delta t`, ``self.dt``,
    by calling :func:`assign_variable`.
    
    :param dt:   time step
    """
    s = "::: initializing time step :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.time_step, dt)
  
  def init_lat(self, lat):
    r"""
    Set grid latitude ``self.lat``
    by calling :func:`assign_variable`.
    
    :param lat:   grid latitude values
    """
    s = "::: initializing grid latitude :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.lat, lat)
  
  def init_lon(self, lon):
    r"""
    Set grid longitude ``self.lon``
    by calling :func:`assign_variable`.
    
    :param lon:   grid longitude values
    """
    s = "::: initializing grid longitude :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.lon, lon)
  
  def init_M_ii(self, M_ii):
    r"""
    Set membrane-stress balance :math:`M_{ii}`, ``self.M_ii``,
    by calling :func:`assign_variable`.
    
    :param M_ii:   membrane-stress balance :math:`M_{ii}`
    """
    s = "::: initializing membrane-stress balance M_ii :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_ii, M_ii)
  
  def init_M_ij(self, M_ij):
    r"""
    Set membrane-stress balance :math:`M_{ij}`, ``self.M_ij``,
    by calling :func:`assign_variable`.
    
    :param M_ij:   membrane-stress balance :math:`M_{ij}`
    """
    s = "::: initializing membrane-stress balance M_ij :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_ij, M_ij)
  
  def init_M_iz(self, M_iz):
    r"""
    Set membrane-stress balance :math:`M_{iz}`, ``self.M_iz``,
    by calling :func:`assign_variable`.
    
    :param M_iz:   membrane-stress balance :math:`M_{iz}`
    """
    s = "::: initializing membrane-stress balance M_iz :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_iz, M_iz)
  
  def init_M_ji(self, M_ji):
    r"""
    Set membrane-stress balance :math:`M_{ji}`, ``self.M_ji``,
    by calling :func:`assign_variable`.
    
    :param M_ji:   membrane-stress balance :math:`M_{ji}`
    """
    s = "::: initializing membrane-stress balance M_ji :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_ji, M_ji)
  
  def init_M_jj(self, M_jj):
    r"""
    Set membrane-stress balance :math:`M_{jj}`, ``self.M_jj``,
    by calling :func:`assign_variable`.
    
    :param M_jj:   membrane-stress balance :math:`M_{jj}`
    """
    s = "::: initializing membrane-stress balance M_jj :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_jj, M_jj)
  
  def init_M_jz(self, M_jz):
    r"""
    Set membrane-stress balance :math:`M_{jz}`, ``self.M_jz``,
    by calling :func:`assign_variable`.
    
    :param M_jz:   membrane-stress balance :math:`M_{jz}`
    """
    s = "::: initializing membrane-stress balance M_jz :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_jz, M_jz)
  
  def init_M_zi(self, M_zi):
    r"""
    Set membrane-stress balance :math:`M_{zi}`, ``self.M_zi``,
    by calling :func:`assign_variable`.
    
    :param M_zi:   membrane-stress balance :math:`M_{zi}`
    """
    s = "::: initializing membrane-stress balance M_zi :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_zi, M_zi)
  
  def init_M_zj(self, M_zj):
    r"""
    Set membrane-stress balance :math:`M_{zj}`, ``self.M_zj``,
    by calling :func:`assign_variable`.
    
    :param M_zj:   membrane-stress balance :math:`M_{zj}`
    """
    s = "::: initializing membrane-stress balance M_zj :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_zj, M_zj)
  
  def init_M_zz(self, M_zz):
    r"""
    Set membrane-stress balance :math:`M_{zz}`, ``self.M_zz``,
    by calling :func:`assign_variable`.
    
    :param M_zz:   membrane-stress balance :math:`M_{zz}`
    """
    s = "::: initializing membrane-stress balance M_zz :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.M_zz, M_zz)
  
  def init_N_ii(self, N_ii):
    r"""
    Set membrane stress :math:`N_{ii}`, ``self.N_ii``,
    by calling :func:`assign_variable`.
    
    :param N_ii:   membrane-stress :math:`N_{ii}`
    """
    s = "::: initializing N_ii :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_ii, N_ii)
  
  def init_N_ij(self, N_ij):
    r"""
    Set membrane stress :math:`N_{ij}`, ``self.N_ij``,
    by calling :func:`assign_variable`.
    
    :param N_ij:   membrane-stress :math:`N_{ij}`
    """
    s = "::: initializing N_ij :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_ij, N_ij)
  
  def init_N_iz(self, N_iz):
    r"""
    Set membrane stress :math:`N_{iz}`, ``self.N_iz``,
    by calling :func:`assign_variable`.
    
    :param N_iz:   membrane-stress :math:`N_{iz}`
    """
    s = "::: initializing N_iz :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_iz, N_iz)
  
  def init_N_ji(self, N_ji):
    r"""
    Set membrane stress :math:`N_{ji}`, ``self.N_ji``,
    by calling :func:`assign_variable`.
    
    :param N_ji:   membrane-stress :math:`N_{ji}`
    """
    s = "::: initializing N_ji :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_ji, N_ji)
  
  def init_N_jj(self, N_jj):
    r"""
    Set membrane stress :math:`N_{jj}`, ``self.N_jj``,
    by calling :func:`assign_variable`.
    
    :param N_jj:   membrane-stress :math:`N_{jj}`
    """
    s = "::: initializing N_jj :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_jj, N_jj)
  
  def init_N_jz(self, N_jz):
    r"""
    Set membrane stress :math:`N_{jz}`, ``self.N_jz``,
    by calling :func:`assign_variable`.
    
    :param N_jz:   membrane-stress :math:`N_{jz}`
    """
    s = "::: initializing N_jz :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_jz, N_jz)
  
  def init_N_zi(self, N_zi):
    r"""
    Set membrane stress :math:`N_{zi}`, ``self.N_zi``,
    by calling :func:`assign_variable`.
    
    :param N_zi:   membrane-stress :math:`N_{zi}`
    """
    s = "::: initializing N_zi :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_zi, N_zi)
  
  def init_N_zj(self, N_zj):
    r"""
    Set membrane stress :math:`N_{zj}`, ``self.N_zj``,
    by calling :func:`assign_variable`.
    
    :param N_zj:   membrane-stress :math:`N_{zj}`
    """
    s = "::: initializing N_zj :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_zj, N_zj)
  
  def init_N_zz(self, N_zz):
    r"""
    Set membrane stress :math:`N_{zz}`, ``self.N_zz``,
    by calling :func:`assign_variable`.
    
    :param N_zz:   membrane-stress :math:`N_{zz}`
    """
    s = "::: initializing N_zz :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.N_zz, N_zz)

  def init_alpha(self, alpha):
    r"""
    Set temperate-zone-marking coefficient :math:`\alpha`, ``self.alpha``,
    by calling :func:`assign_variable`.
   
    :param alpha:  temperate-zone-marking coefficient 
    """
    s = "::: initializing temperate-zone-marking coefficient :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.alpha, alpha)

  def init_alpha_int(self, alpha_int):
    r"""
    Set vertical integral of temperate zone marking coefficient 
    :math:`\int \alpha dz`, ``self.alpha_int``,
    by calling :func:`assign_variable`.
    
    :param alpha_int:  vertical integral of temperate-zone-marking coefficient 
    """
    s = "::: initializing temperate-zone thickness :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.alpha_int, alpha_int)

  def init_Fb(self, Fb):
    r"""
    Set basal-water discharge :math:`F_b`, ``self.Fb``,
    by calling :func:`assign_variable`.
    
    :param Fb:   basal-water discharge
    """
    s = "::: initializing basal-water discharge :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Fb, Fb)

  def init_Wbar(self, Wbar):
    r"""
    Set vertically-averaged water content :math:`\bar{W}`, ``self.Wbar``.
    by calling :func:`assign_variable`.
    
    :param Wbar:   vertically-averaged water content
    """
    s = "::: initializing vertically averaged water content :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Wbar, Wbar)

  def init_temp_rat(self, temp_rat):
    r"""
    Set ratio of temperate ice :math:`\frac{1}{H}\int \alpha dz`, 
    ``self.temp_rat``,
    by calling :func:`assign_variable`.
    
    :param temp_rat:   ratio of column that is temperate
    """
    s = "::: initializing temperate zone ratio :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.temp_rat, temp_rat)

  def init_Qbar(self, Qbar):
    r"""
    Set vertically-averaged strain heat :math:`\bar{Q}`, ``self.Qbar``,
    by calling :func:`assign_variable`.
    
    :param Qbar:   vertically-averaged strain heat
    """
    s = "::: initializing vertically-averaged strain-heat :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Qbar, Qbar)

  def init_PE(self, PE):
    r"""
    Set element Peclet number :math:`P_e`, ``self.PE``,
    by calling :func:`assign_variable`.
    
    :param PE:   grid Peclet number
    """
    s = "::: initializing grid Peclet number :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.PE, PE)

  def init_n_f(self, n_f):
    r"""
    Set outward-normal vector array :math:`\mathbf{n}``, ``self.n_f``,
    by calling :func:`assign_variable`.
    
    :param n_f:   vector of outward-pointing normal values
    """
    s = "::: initializing outward-normal-vector function n_f :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.n_f, n)

  def init_Fb_bounds(self, Fb_min, Fb_max):
    r"""
    Set upper and lower bounds for basal-water discharge :math:`F_b^{\max}` 
    and :math:`F_b^{\min}`,``self.Fb_max``, ``self.Fb_min``, respectively,
    by calling :func:`assign_variable`.
    
    :param Fb_min: lower bound for basal-water discharge ``self.Fb``
    :param Fb_max: upper bound for basal-water discharge ``self.Fb``
    """
    s = "::: initializing bounds for basal-water discharge Fb :::"
    print_text(s, cls=self.this)
    self.init_Fb_min(Fb_min, cls)
    self.init_Fb_max(Fb_max, cls)

  def init_Fb_min(self, Fb_min):
    r"""
    Set lower bound of basal water discharge :math:`F_b`, ``self.Fb_min``,
    by calling :func:`assign_variable`.
    
    :param Fb_min: lower bound for basal-water discharge ``self.Fb``
    """
    s = "::: initializing lower bound for basal water flux Fb :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Fb_min, Fb_min)

  def init_Fb_max(self, Fb_max):
    r"""
    Set upper bound of basal-water discharge :math:`F_b`, ``self.Fb_max``,
    by calling :func:`assign_variable`.
    
    :param Fb_max: upper bound for basal-water discharge ``self.Fb``
    """
    s = "::: initializing upper bound for basal water flux Fb :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.Fb_max, Fb_max)

  def init_k_0(self, k_0):
    r"""
    Set non-advective water-flux coefficient :math:`k_0`, ``self.k_0``,
    by calling :func:`assign_variable`.
    
    :param k_0:   non-advective water-flux coefficient
    """
    s = "::: initializing non-advective flux coefficient k_0 :::"
    print_text(s, cls=self.this)
    self.assign_variable(self.k_0, k_0)
  
  def init_lam_basal_pressure(self):
    r"""
    Initialize the basal normal stress ``self.lam`` to cryostatic pressure 
    :math:`\rho g (S - B)`.
    """
    p = project(self.rhoi * self.g * (self.S - self.B), self.Q)
    self.init_lam(p)

  def init_beta_SIA(self, U_mag=None, eps=0.5):
    r"""
    Init basal-traction :math:`\beta`, ``self.beta``, from 

    .. math::

       \beta \Vert \mathbf{u}_B \Vert = \rho g H \Vert \nabla S \Vert,
    
    the shallow ice approximation, using the observed surface velocity 
    ``U_mag`` as approximate basal velocity,
    
    .. math::

       \beta_{\text{SIA}} = \frac{\rho g H \Vert \nabla S \Vert}{\Vert \mathbf{u}_B \Vert + \epsilon}

    :param U_mag: basal-velocity :math:`\mathbf{u}_B` magnitude.
    :param eps:   minimum velocity :math:`\epsilon` introduced 
                  to prevent singularity, default is 0.5 m/a.

    If ``U_mag`` is ``None``, the basal velocity :math:`\mathbf{u}_B` is 
    defined from :math:`\mathbf{u}_{ob}` as given by ``self.U_ob``.  Any 
    gaps in obervation data defined by ``self.Uob_missing_dofs`` 
    (see :func:`init_U_mask`) are set to values defined by balance-velocity 
    magnitude :math:`\bar{u}` as given by ``self.Ubar``.
    
    """
    s = "::: initializing beta from SIA :::"
    print_text(s, cls=self.this)
    Q        = self.Q
    rhoi     = self.rhoi
    g        = self.g
    gradS    = grad(self.S)
    H        = self.S - self.B
    U_s      = Function(Q, name='U_s')
    if U_mag == None:
      U_v                        = self.U_ob.vector().array()
      Ubar_v                     = self.Ubar.vector().array()
      U_v[self.Uob_missing_dofs] = Ubar_v[self.Uob_missing_dofs]
    else:
      U_v = U_mag.vector().array()
    U_v[U_v < eps] = eps
    self.assign_variable(U_s, U_v)
    S_mag    = sqrt(inner(gradS, gradS) + DOLFIN_EPS)
    beta_0   = project((rhoi*g*H*S_mag) / U_s, Q, annotate=False)
    beta_0_v = beta_0.vector().array()
    beta_0_v[beta_0_v < 1e-2] = 1e-2
    self.betaSIA = Function(Q, name='betaSIA')
    self.assign_variable(self.betaSIA, beta_0_v)
    
    if self.dim == 3:
      self.assign_variable(self.beta, DOLFIN_EPS)
      bc_beta = DirichletBC(self.Q, self.betaSIA, self.ff, self.GAMMA_B_GND)
      bc_beta.apply(self.beta.vector())
      #self.assign_variable(self.beta, self.betaSIA)
    elif self.dim == 2:
      self.assign_variable(self.beta, self.betaSIA)
    print_min_max(self.beta, 'beta')
      
  def init_beta_stats(self, mdl='Ubar', use_temp=False, mode='steady'):
    """
    It's complicated.
    """
    s    = "::: initializing beta from stats :::"
    print_text(s, cls=self.this)
    
    q_geo  = self.q_geo
    T_s    = self.T_surface
    adot   = self.adot
    Mb     = self.Mb
    Ubar   = self.Ubar
    Q      = self.Q
    B      = self.B
    S      = self.S
    T      = self.T
    T_s    = self.T_surface
    rho    = self.rhoi
    g      = self.g
    H      = S - B

    Ubar_v = Ubar.vector().array()
    Ubar_v[Ubar_v < 1e-10] = 1e-10
    self.assign_variable(Ubar, Ubar_v)
           
    D      = Function(Q, name='D')
    B_v    = B.vector().array()
    D_v    = D.vector().array()
    D_v[B_v < 0] = B_v[B_v < 0]
    self.assign_variable(D, D_v)

    gradS = as_vector([S.dx(0), S.dx(1), 0.0])
    gradB = as_vector([B.dx(0), B.dx(1), 0.0])
    gradH = as_vector([H.dx(0), H.dx(1), 0.0])

    nS   = sqrt(inner(gradS, gradS) + DOLFIN_EPS)
    nB   = sqrt(inner(gradB, gradB) + DOLFIN_EPS)
    nH   = sqrt(inner(gradH, gradH) + DOLFIN_EPS)
    
    #if mdl == 'Ubar':
    #  u_x    = -rho * g * H * S.dx(0)
    #  v_x    = -rho * g * H * S.dx(1)
    #  U_i    = as_vector([u_x,  v_x, 0.0])
    #  U_j    = as_vector([v_x, -u_x, 0.0])
    #elif mdl == 'U' or mdl == 'U_Ubar':
    #  U_i    = as_vector([self.u,  self.v, 0.0])
    #  U_j    = as_vector([self.v, -self.u, 0.0])
    U_i    = as_vector([self.u,  self.v, 0.0])
    U_j    = as_vector([self.v, -self.u, 0.0])
    Umag   = sqrt(inner(U_i,U_i) + DOLFIN_EPS)
    Uhat_i = U_i / Umag
    Uhat_j = U_j / Umag

    dBdi = dot(gradB, Uhat_i)
    dBdj = dot(gradB, Uhat_j)
    dSdi = dot(gradS, Uhat_i)
    dSdj = dot(gradS, Uhat_j)
    dHdi = dot(gradH, Uhat_i)
    dHdj = dot(gradH, Uhat_j)

    ini  = sqrt(rho * g * H * nS / (Umag + 0.1))

    x0   = S
    x1   = T_s
    x2   = nS
    x3   = D
    x4   = nB
    x5   = H
    x6   = q_geo
    x7   = adot
    x8   = T
    x9   = Mb
    x10  = self.u
    x11  = self.v
    x12  = self.w
    x13  = ln(Ubar + DOLFIN_EPS)
    x14  = ln(Umag + DOLFIN_EPS)
    x15  = ini
    x16  = dBdi
    x17  = dBdj
    x18  = dSdi
    x19  = dSdj
    x20  = nH
    x21  = self.tau_id
    x22  = self.tau_jd
    x23  = self.tau_ii
    x24  = self.tau_ij
    x25  = self.tau_ji
    x26  = self.tau_jj

    names = ['S', 'T_s', 'gradS', 'D', 'gradB', 'H', 'q_geo', 'adot', 'T',
             'Mb', 'u', 'v', 'w', 'ln(Ubar)', 'ln(Umag)', 'ini',
             'dBdi', 'dBdj', 'dSdi', 'dSdj', 'nablaH', 'tau_id', 'tau_jd',
             'tau_ii', 'tau_ij', 'tau_ji', 'tau_jj']
    names = np.array(names)

    if mdl == 'Ubar':
      if not use_temp:
        X    = [x0,x1,x5,x7,x13,x16,x18]
        idx  = [ 0, 1, 5, 7, 13, 16, 18]
        bhat = [ -1.01661102e+02,   6.59472291e-03,   8.34479667e-01,
                 -3.20751595e-04,  -1.86910058e+00,  -1.50122785e-01,
                 -1.61283407e+01,   3.42099244e+01,  -1.38190017e-07,
                 -2.42124307e-05,   5.28420031e-08,  -5.71485389e-05,
                 -3.75168897e-06,   6.62615357e-04,  -2.09616017e-03,
                 -1.63919106e-03,  -4.67468432e-07,   7.70150910e-03,
                 -1.06827565e-05,   5.82852747e-02,  -1.59176855e-01,
                  2.60703978e-08,   1.12176250e-04,  -9.96266233e-07,
                  1.54898171e-04,  -7.75201260e-03,  -3.97881378e-02,
                 -9.66212690e-04,  -6.88656946e-01,   2.86508703e+00,
                 -4.77406074e-03,   4.46234782e-03,  -9.93937326e-02,
                 -1.11058398e+01,   1.19703551e+01,  -3.46378138e+01]
        #bhat = [ -1.06707322e+02,   6.93681939e-03,   8.72090381e-01,
        #         -2.05377136e-04,  -1.68695225e+00,  -1.54427603e-01,
        #         -1.48494954e+01,   3.13320531e+01,  -1.46372911e-07,
        #         -2.54809386e-05,   5.58213888e-08,  -5.05686875e-05,
        #         -3.57485925e-06,   6.74423417e-04,  -1.90332998e-03,
        #         -1.70912922e-03,  -9.14015814e-07,   6.90894685e-03,
        #          5.38728829e-06,   5.52828014e-02,  -1.49677701e-01,
        #          2.10321794e-08,   1.26574205e-04,  -1.58804814e-06,
        #         -1.07066137e-04,  -6.59781673e-03,  -4.21221477e-02,
        #         -9.11842753e-04,  -5.91089434e-01,   2.37465616e+00,
        #         -4.79794725e-03,  -1.20787950e-03,  -8.37001425e-02,
        #         -1.35364012e+01,   2.01047113e+01,  -3.48057200e+01]
     
      else: 
        X    = [x0,x1,x5,x7,x8,x9,x13,x16,x18]
        idx  = [ 0, 1, 5, 7, 8, 9, 13, 16, 18]
        bhat = [  1.99093750e+01,  -9.37152784e-04,  -1.53849816e-03,
                 -2.72682710e-03,   3.11376629e+00,  -6.22550705e-02,
                 -4.78841821e+02,   1.18870083e-01,   1.46462501e+01,
                  4.73228083e+00,  -1.23039512e-05,   4.80948459e-08,
                 -1.75152253e-04,   1.57869882e-05,  -1.85979092e-03,
                 -5.31979350e-06,  -2.94994855e-04,  -2.88696470e-03,
                  9.87920894e-06,  -1.67014309e-02,   1.38310308e-05,
                  1.29911016e+00,   8.79462642e-06,   2.58486129e-02,
                  4.59079956e-01,  -1.62460133e-04,   8.39672735e-07,
                 -1.44977594e-02,   5.58957555e-07,   7.38625502e-04,
                 -9.92789432e-03,   6.02766800e-03,   2.74638935e-01,
                 -7.24036641e-05,  -4.63126335e-01,   2.92369712e+00,
                  5.07887934e-01,  -4.57929508e-04,  -8.33728342e-02,
                 -4.71625234e-01,  -5.85160316e-02,  -1.74723504e+01,
                 -1.83509536e+01,   5.35514345e-04,  -8.46507380e-02,
                 -1.60127263e+01]
    
    elif mdl == 'U':
      if not use_temp:
        X    = [x0,x1,x5,x7,x14,x16,x18]
        idx  = [ 0, 1, 5, 7, 14, 16, 18]
        bhat = [ -9.28289389e+01,   5.73687339e-03,   7.33526290e-01,
                  2.76998568e-03,  -1.08656857e-01,  -1.08545047e+00,
                 -1.50267782e+01,  -7.04864127e+01,  -7.76085391e-08,
                 -2.17802438e-05,  -4.99587467e-08,   5.87139196e-05,
                  1.64670170e-05,   1.06212966e-04,   7.11755177e-05,
                 -1.37677776e-03,  -9.08932836e-06,   3.60621065e-04,
                  2.97118032e-03,   5.50814766e-02,   2.21044611e-01,
                 -1.15497725e-07,   8.63993130e-05,  -2.12395318e-06,
                  7.21699958e-04,  -1.09346933e-02,  -3.12224072e-02,
                 -2.39690796e-02,  -2.95080157e-01,  -3.40502802e-01,
                 -2.62000881e-02,  -1.78157283e-02,   7.19763432e-02,
                 -1.94919730e+00,  -9.82413027e+00,  -7.61245200e+01]
      else:
        X    = [x0,x1,x5,x7,x8,x9,x14,x16,x18]
        idx  = [ 0, 1, 5, 7, 8, 9, 14, 16, 18]
        bhat = [  2.09623581e+01,   6.66919839e-04,  -7.02196170e-02,
                 -1.15080308e-03,   5.34783070e+00,  -7.11388758e-02,
                 -4.07361631e+01,   1.02018632e+00,  -1.86900651e+01,
                 -4.20181324e+01,  -9.26143019e-06,  -7.72058925e-08,
                 -4.15062408e-05,   7.02170069e-06,   2.70372865e-03,
                 -1.37333418e-05,   8.87920333e-05,   1.42938174e-03,
                  7.77557165e-06,  -2.35402146e-02,   3.04680358e-04,
                 -1.71597355e-01,   1.40252311e-04,   4.10097716e-02,
                  2.55567246e-01,  -1.33628767e-07,  -2.15459028e-06,
                  6.29599393e-05,  -4.11071912e-05,   1.28619782e-03,
                 -1.46657539e-02,   3.09279801e-03,  -2.27450062e-01,
                 -7.40025166e-03,  -5.06709113e-01,  -6.76120111e-01,
                  3.10802402e-01,  -5.34552872e-03,   2.19914707e-02,
                 -1.40943367e-01,   3.07890125e-01,  -9.03508676e+00,
                  8.27529346e+01,   6.60448755e-03,   2.42989633e+00,
                 -4.31461210e+01]
    
    elif mdl == 'U_Ubar':
      if not use_temp:
        X    = [x0,x1,x5,x7,x13,x14,x16,x18]
        idx  = [ 0, 1, 5, 7, 13, 14, 16, 18]
        bhat = [ -9.25221622e+01,   5.70295987e-03,   7.30768422e-01,
                  2.75877006e-03,   7.37861453e-02,  -2.93985236e-03,
                 -1.07390793e+00,  -1.45320123e+01,  -7.18521246e+01,
                 -7.86411913e-08,  -2.15769127e-05,  -4.80926515e-08,
                  5.56842889e-05,   1.28402687e-06,   1.12826733e-05,
                  9.07581727e-05,  -7.62357377e-05,  -1.37165484e-03,
                 -8.99331396e-06,  -3.36292037e-04,   4.24771193e-05,
                  2.97610385e-03,   5.34869351e-02,   2.28993842e-01,
                 -1.17987943e-07,   8.26468590e-05,   2.32815553e-06,
                 -6.66323072e-06,   6.73934903e-04,  -1.12192482e-02,
                 -3.22339742e-02,  -3.78492901e-04,  -2.38023512e-02,
                 -2.88687981e-01,  -4.11715791e-01,   3.06665249e-04,
                  3.29695662e-04,   4.96515338e-03,   1.28914720e-02,
                 -2.83133687e-02,  -3.08127082e-02,  -3.19074160e-02,
                 -1.60977763e+00,  -1.10451113e+01,  -7.66011531e+01]
      else:
        X    = [x0,x1,x5,x7,x8,x9,x13,x14,x16,x18]
        idx  = [ 0, 1, 5, 7, 8, 9, 13, 14, 16, 18]
        bhat = [  1.95228446e+01,   6.59477606e-04,  -6.45139002e-02,
                 -1.10071394e-03,   5.13699019e+00,  -6.45652015e-02,
                 -5.14739582e+01,  -3.68769001e-03,   9.57519905e-01,
                 -1.77507405e+01,  -4.37983921e+01,  -9.02491948e-06,
                 -7.61384926e-08,  -3.73066416e-05,   6.79516468e-06,
                  2.83564402e-03,  -4.68103812e-07,  -1.20747491e-05,
                  4.00845895e-05,   1.67755582e-03,   7.73371401e-06,
                 -2.23470170e-02,   2.78775317e-04,  -1.61211932e-01,
                  4.64633086e-05,   4.37335336e-04,   4.27466758e-02,
                  2.50573113e-01,  -4.81341231e-06,  -2.31708961e-06,
                 -1.68503900e-04,   3.54318161e-06,  -4.20165147e-05,
                  1.26878513e-03,  -1.54490818e-02,   2.66749014e-03,
                 -2.98194766e-01,  -2.92113296e-04,  -4.31378498e-03,
                 -4.83721711e-01,  -7.30055588e-01,   3.42250813e-01,
                 -3.22616161e-05,  -5.40195432e-03,   1.73408633e-02,
                 -1.31066469e-01,   9.73640123e-03,   2.61368301e-01,
                 -9.93273895e+00,   8.31773699e+01,  -5.74031885e-04,
                  9.54289863e-03,  -3.57353698e-02,   3.62295735e-03,
                  2.54399352e+00,  -4.21129483e+01]
    
    elif mdl == 'stress':
      X    = [x0,x1,x5,x7,x14,x16,x18,x21,x23,x24,x25,x26]
      idx  = [ 0, 1, 5, 7, 14, 16, 18, 21, 23, 24, 25, 26]
      bhat = [  5.47574225e+00,   9.14001489e-04,  -1.03229081e-03,
               -7.04987042e-04,   2.15686223e+00,  -1.52869679e+00,
               -1.74593819e+01,  -2.05459701e+01,  -1.23768850e-05,
                2.01460255e-05,   1.97622781e-05,   3.68067438e-05,
                6.63468606e-06,  -3.69046174e-06,  -4.47828887e-08,
               -3.67070759e-05,   2.53827543e-05,  -1.88069561e-05,
                2.05942231e-03,  -5.95566325e-10,   1.00881255e-09,
                6.11553989e-10,  -4.11737126e-10,   6.27370976e-10,
                3.42275389e-06,  -8.17017771e-03,   4.01803819e-03,
                6.78767571e-02,   4.29444354e-02,   4.45551518e-08,
               -8.23509210e-08,  -7.90182526e-08,  -1.48650850e-07,
               -2.36138203e-08,  -4.75130905e-05,  -1.81655894e-05,
                9.79852186e-04,  -1.49411705e-02,  -2.35701903e-10,
                2.32406866e-09,   1.48224703e-09,  -1.09016625e-09,
               -1.31162142e-09,   1.47593911e-02,  -1.84965301e-01,
               -1.62413731e-01,   2.38867744e-07,   2.09579112e-07,
                6.11572155e-07,   1.44891826e-06,  -4.94537953e-07,
               -3.30400642e-01,   7.93664407e-01,   7.76571489e-08,
               -1.64476914e-07,  -2.13414311e-07,   4.75810302e-07,
                2.55787543e-07,  -6.37972323e+00,  -3.77364196e-06,
                8.65062737e-08,   6.13207853e-06,   8.39233482e-07,
               -3.76402983e-06,  -2.02633500e-05,  -7.28788200e-06,
               -2.72030382e-05,  -1.33298507e-05,   1.11838930e-05,
                9.74762098e-14,  -2.37844072e-14,  -1.11310490e-13,
                8.91237008e-14,   1.16770903e-13,   5.77230478e-15,
               -4.87322338e-14,   9.62949381e-14,  -2.12122129e-13,
                1.55871983e-13]
   
    for xx,nam in zip(X, names[idx]):
      print_min_max(xx, nam)

    X_i  = []
    X_i.extend(X)
     
    for i,xx in enumerate(X):
      if mdl == 'Ubar' or mdl == 'U' and not use_temp:
        k = i
      else:
        k = i+1
      for yy in X[k:]:
        X_i.append(xx*yy)
    
    #self.beta_f = exp(Constant(bhat[0]))
    self.beta_f = Constant(bhat[0])
    
    for xx,bb in zip(X_i, bhat[1:]):
      self.beta_f += Constant(bb)*xx
      #self.beta_f *= exp(Constant(bb)*xx)
    self.beta_f = exp(self.beta_f)**2
    
    #if mode == 'steady':
    #  beta0                   = project(self.beta_f, Q, annotate=False)
    #  beta0_v                 = beta0.vector().array()
    #  beta0_v[beta0_v < 1e-2] = 1e-2
    #  self.assign_variable(beta0, beta0_v)
    #
    #  self.assign_variable(self.beta, 1e-2)
    #  bc_beta = DirichletBC(self.Q, beta0, self.ff, self.GAMMA_B_GND)
    #  bc_beta.apply(self.beta.vector())
    
    if mode == 'steady':
      beta0  = project(self.beta_f, Q, annotate=False)
      beta0_v                 = beta0.vector().array()
      beta0_v[beta0_v < DOLFIN_EPS] = DOLFIN_EPS
      self.init_beta(beta0_v)
    elif mode == 'transient':
      self.assign_variable(self.beta, 200.0)
    
    print_min_max(self.beta, 'beta_hat')
 
  def update_stats_beta(self):
    """
    Re-compute the statistical friction field and save into ``self.beta``.
    """
    s    = "::: updating statistical beta :::"
    print_text(s, self.D3Model_color)
    beta   = project(self.beta_f, self.Q, annotate=False)
    beta_v = beta.vector().array()
    ##betaSIA_v = self.betaSIA.vector().array()
    ##beta_v[beta_v < 10.0]   = betaSIA_v[beta_v < 10.0]
    beta_v[beta_v < 0.0]    = 0.0
    #beta_v[beta_v > 2500.0] = 2500.0
    self.assign_variable(self.beta, beta_v)
     
  def form_energy_dependent_rate_factor(self):
    r"""
    formulates energy-dependent rate factor :math:`A`, ``self.A``, from

    .. math::

      A(\theta) = a_T E \left( 1 + 181.5 W_f \right) \exp\left(-\frac{Q_T}{RT'} \right),
    
    with energy :math:`\theta` defined by ``self.theta``, enhancement 
    factor :math:`E` given by ``self.E``, universal gas constant 
    :math:`R` given by ``self.R``, empirically-constrained water 
    content :math:`W_f = \min\{W, 0.01\}`, energy-dependent flow-parameter

    .. math::

      a_T &= \begin{cases}
               3.985 \times 10^{-13} \hspace{3mm} \text{s}^{-1}\text{Pa}^{-3} & T' < 263.15 \\
               1.916 \times 10^{3\hphantom{-1}} \hspace{3mm} \text{s}^{-1}\text{Pa}^{-3} & T' \geq 263.15 \\
             \end{cases},

    temperature-dependent creep activation energy 

    .. math::

      Q_T & = \begin{cases}
                6.00 \times 10^{4} \hspace{3mm} \text{J mol}^{-1} & T' < 263.15 \\
                1.39 \times 10^{5} \hspace{3mm} \text{J mol}^{-1} & T' \geq 263.15 \\
              \end{cases},
    
    temperature :math:`T` given by ``self.T``, and pressure-adjusted
    temperature :math:`T'` given by ``self.Tp``.
    """
    s = "::: formulating energy-dependent rate-factor :::"
    print_text(s, cls=self.this)
    
    Tp          = self.Tp
    W           = self.W
    R           = self.R
    E           = self.E
    a_T         = conditional( lt(Tp, 263.15),  self.a_T_l, self.a_T_u)
    Q_T         = conditional( lt(Tp, 263.15),  self.Q_T_l, self.Q_T_u)
    W_T         = conditional( lt(W,  0.01),    W,          0.01)
    self.A      = E*a_T*(1 + 181.25*W_T)*exp(-Q_T/(R*Tp))

  def calc_A(self):
    """
    calculates flow-rate factor ``self.A``, set to ``self.A``.
    """
    Tp          = self.Tp
    W           = self.W
    R           = self.R
    E           = self.E
    a_T         = conditional( lt(Tp, 263.15),  self.a_T_l, self.a_T_u)
    Q_T         = conditional( lt(Tp, 263.15),  self.Q_T_l, self.Q_T_u)
    W_T         = conditional( lt(W,  0.01),    W,          0.01)
    A           = E*a_T*(1 + 181.25*W_T)*exp(-Q_T/(R*Tp))
    self.A      = A
 
  def calc_eta(self, epsdot):
    r"""
    Calculates viscosity :math:`\eta`, set to ``self.eta``, given by 
  
    .. math::
  
      \eta(\theta, \mathbf{u}) = \frac{1}{2}A(\theta)^{-\frac{1}{n}} (\dot{\varepsilon}_e(\mathbf{u}) + \dot{\varepsilon}_0)^{\frac{1-n}{n}},

    for energy :math:`\theta` given by ``self.theta``, flow-rate factor 
    :math:`A` given by ``self.A``, strain-rate regularization
    :math:`\dot{\varepsilon}_0` given by ``self.eps_reg``, and Glen's flow 
    parameter :math:`n` given by ``self.n``.

    :param epsdot: effective-strain rate :math:`\dot{\varepsilon}_e(\mathbf{u})`
    """
    s     = "::: calculating viscosity :::"
    print_text(s, cls=self.this)
    eps_reg = self.eps_reg
    A       = self.A
    n       = self.n

    # calculate viscosity :
    eta     = 0.5 * A**(-1/n) * (epsdot + eps_reg)**((1-n)/(2*n))
    self.eta = eta

  def calc_vert_average(self, u):
    """
    Calculate the vertical average of the function ``u``.

    This method must be overwritten by the class inheriting this class.
    
    :param u: function to be vertically averaged
    :rtype:   the resulting vertical average of ``u``.
    """
    raiseNotDefined()

  def calc_normal_vector(self):
    """
    Calculates the outward-pointing normal vector as a FEniCS function.
    This could then be used in any :class:`~fenics.DirichletBC`.
    Saved to ``self.n_f``.
    """
    s     = "::: calculating normal-vector function :::"
    print_text(s, cls=self.this)

    n       = self.N
    n_trial = TrialFunction(self.V)
    n_test  = TestFunction(self.V)

    a = inner(n_trial, n_test)*dx
    L = inner(n,       n_test)*ds

    A = assemble(a, keep_diagonal=True)
    A.ident_zeros() # Regularize the matrix
    b = assemble(L)

    n = Function(self.V)
    solve(A, n.vector(), b, 'cg', 'amg')
    
    area = assemble(Constant(1.0)*ds(self.mesh))
    nds  = assemble(inner(n, n)*ds)
    s = "    - average value of normal on boundary: %.3f - " % (nds / area)
    print_text(s, cls=self.this)
    
    self.init_n_f(n)

  def get_xy_velocity_angle(self, U):
    r"""
    Calculates the angle in radians of the horizontal velocity vector 
    :math:`\mathbf{u}_h = [u\ v]^\intercal` from the x-axis.

    :param U: horizontal velocity vector :math:`\mathbf{u}_h = [u\ v]^\intercal`
    :rtype:  :class:`~fenics.Function` of angle values.
    """
    u,v,w   = U.split(True)
    u_v     = u.vector().array()
    v_v     = v.vector().array()
    theta_v = np.arctan2(v_v, u_v)
    Q       = u.function_space()
    theta   = Function(Q, name='theta_xy_U_angle')
    self.assign_variable(theta, theta_v)
    return theta

  def get_xz_velocity_angle(self):
    """
    Calculates the angle in radians of the vertical velocity vector 
    :math:`\mathbf{u}_v = [u\ w]^\intercal` from the x-axis.

    :param U: vertical velocity vector :math:`\mathbf{u}_v = [u\ w]^\intercal`
    :rtype:  :class:`~fenics.Function` of angle values.
    """
    u,v,w   = self.U3.split(True)
    u_v     = u.vector().array()
    w_v     = w.vector().array()
    theta_v = np.arctan2(w_v, u_v)
    theta   = Function(self.Q, name='theta_xz_U_angle')
    self.assign_variable(theta, theta_v)
    return theta

  def z_rotation_matrix(self, theta):
    """
    Form the rotation matrix :math:`R_z` about the :math:`z` axes 
    by angle ``theta``.

    :param theta: angle in radians to rotate about the :math:`z`-axis
    :rtype:       :class:`~fenics.Matrix` :math:`R_z`
    """
    c  = cos(theta)
    s  = sin(theta)
    Rz = as_matrix([[c, -s, 0],
                    [s,  c, 0],
                    [0,  0, 1]])
    return Rz

  def y_rotation_matrix(self, theta):
    """
    Form the rotation matrix :math:`R_y` about the :math:`y` axes 
    by angle ``theta``.

    :param theta: angle in radians to rotate about the :math:`y`-axis
    :rtype:       :class:`~fenics.Matrix` :math:`R_y`
    """
    c  = cos(theta)
    s  = sin(theta)
    Ry = as_matrix([[ c, 0, s],
                    [ 0, 1, 0],
                    [-s, 0, c]])
    return Ry

  def rotate_tensor(self, M, R):
    """
    Rotate the tnesor ``M`` by the rotation matrix ``R``.

    if ``M`` is a rank-two tensor,

    .. math::

      M_r = R \cdot M \cdot R

    if ``M`` is a rank-one tensor,

    .. math::

      M_r = R \cdot M

    :param M:     :class:`~fenics.Matrix` or :class:`~fenics.Tensor` to be 
                  rotated
    :param R:     rotation :class:`~fenics.Matrix` or :class:`~fenics.Tensor`
    :rtype:       rotated matrix
    """
    if len(M.ufl_shape) == 2:
      Mr = dot(R, dot(M, R.T))
    elif len(M.ufl_shape) == 1:
      Mr = dot(R, M)
    else:
      s   = ">>> METHOD 'rotate_tensor' REQUIRES RANK 2 OR 1 TENSOR <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
    return Mr

  def get_norm(self, U, kind='l2'):
    """
    Calculate and return the norm of and the normalized vector 
    :math:`\hat{\mathbf{u}}`, of the vector :math:`\mathbf{u}` 
    given by parameter ``U``.
    The parameter ``kind`` may be either ``l2`` for the :math:`L^2` 
    norm or ``linf`` for the :math:`L^{\infty}` norm

    :param U:    :class:`~fencics.GenericVector`, list, or tuple of vector
                 components
    :param kind: string
    :rtype:      tuple containing (:math:`\hat{\mathbf{u}}`,
                                   :math:`\Vert \mathbf{u} \Vert`)
    """
    # iterate through each component and convert to array :
    U_v = []
    # TODO: this can be done without split :
    if type(U[0]) == indexed.Indexed:
      U = U.split(True)
    for u in U:
      # convert to array and normailze the components of U :
      u_v = u.vector().array()
      U_v.append(u_v)
    U_v = np.array(U_v)

    # calculate the norm :
    if kind == 'l2':
      norm_u = np.sqrt(np.sum(U_v**2,axis=0))
    elif kind == 'linf':
      norm_u = np.amax(U_v,axis=0)
    
    return U_v, norm_u

  def normalize_vector(self, U):
    """
    Create a normalized vector of the vector :math:`\mathbf{u}` 
    given by parameter ``U``.

    :param U:    :class:`~fencics.GenericVector`, list, or tuple of vector
                 components
    :rtype:      normalized :class:`~fenics.GenericVector`
                 :math:`\hat{\mathbf{u}}` of :math:`\mathbf{u}`
    """
    s   = "::: normalizing vector :::"
    print_text(s, cls=self.this)
    
    Q = U[0].function_space()

    U_v, norm_u = self.get_norm(U)

    norm_u[norm_u <= 0.0] = 1e-15
    
    # normalize the vector :
    U_v /= norm_u
    
    # convert back to fenics :
    U_f = []
    for u_v in U_v:
      u_f = Function(Q, name='u_f')
      self.assign_variable(u_f, u_v)
      U_f.append(u_f)

    # return a UFL vector :
    return as_vector(U_f)

  def assign_submesh_variable(self, u_to, u_from):
    """
    Assign the values from the function ``u_from`` to the function ``u_to``,
    where ``u_from`` and ``u_to`` are defined over non-identical meshes.

    :param u_to:    :class:`~fenics.Function` or :class:`~fenics.GenericVector`
                    to assign to
    :param u_from: :class:`~fenics.Function` or :class:`~fenics.GenericVector`
                   to assign from
    """
    s   = "::: assigning submesh variable :::"
    print_text(s, cls=self.this)
    lg = LagrangeInterpolator()
    lg.interpolate(u_to, u_from)
    print_min_max(u_to, u_to.name())

  def assign_variable(self, u, var, annotate=False):
    """
    Manually assign the values from ``var`` to ``u``.  The parameter ``var``
    may be a string pointing to the location of an :class:`~fenics.XDMFFile`, 
    :class:`~fenics.HDF5File`, or an xml file.

    :param u:        FEniCS :class:`~fenics.Function` assigning to
    :param var:      value assigning from
    :param annotate: allow Dolfin-Adjoint annotation
    :type var:       float, int, :class:`~fenics.Expression`,
                     :class:`~fenics.Constant`, :class:`~fenics.GenericVector`,
                     string, :class:`~fenics.HDF5File`
    :type u:         :class:`~fenics.Function`, :class:`~fenics.GenericVector`,
                     :class:`~fenics.Constant`, float, int
    :type annotate:  bool
    """
    if isinstance(var, float) or isinstance(var, int):
      if    isinstance(u, GenericVector) or isinstance(u, Function) \
         or isinstance(u, dolfin.functions.function.Function):
        u.vector()[:] = var
      elif  isinstance(u, Constant):
        u.assign(var)
      elif  isinstance(u, float) or isinstance(u, int):
        u = var
    
    elif isinstance(var, np.ndarray):
      if var.dtype != np.float64:
        var = var.astype(np.float64)
      u.vector().set_local(var)
      u.vector().apply('insert')
    
    elif isinstance(var, Expression) \
      or isinstance(var, Constant)  \
      or isinstance(var, dolfin.functions.constant.Constant) \
      or isinstance(var, Function) \
      or isinstance(var, dolfin.functions.function.Function) \
      or isinstance(var, GenericVector):
      u.assign(var, annotate=annotate)
      #u.interpolate(var, annotate=annotate)

    #elif isinstance(var, GenericVector):
    #  self.assign_variable(u, var.array(), annotate=annotate)

    elif isinstance(var, str):
      File(var) >> u

    elif isinstance(var, HDF5File):
      var.read(u, u.name())

    else:
      s =  "*************************************************************\n" + \
           "assign_variable() function requires a Function, array, float,\n" + \
           " int, Vector, Expression, Constant, or string path to .xml,\n"   + \
           "not %s.  Replacing object entirely\n" + \
           "*************************************************************"
      print_text(s % type(var) , 'red', 1)
      u = var
    print_min_max(u, u.name())

  def save_hdf5(self, u, f, name=None):
    """
    Save a :class:`~fenics.Function` ``u`` to the .h5 file ``f`` in the 
    ``hdf5`` subdirectory of ``self.out_dir``.  If ``name`` = ``None``, 
    this will save the flie under ``u.name()``.

    :param u: the function to save
    :param f: the file to save to
    :type f:  :class:`~fenics.HDF5File`
    :type u:  :class:`~fenics.Constant`, :class:`~fenics.Function`, or 
              :class:`~fenics.GenericVector`
    """
    if name == None:
      name = u.name()
    s = "::: writing '%s' variable to hdf5 file :::" % name
    print_text(s, 'green')#cls=self.this)
    f.write(u, name)
    print_text("    - done -", 'green')#cls=self.this)

  def save_xdmf(self, u, name, f=None, t=0.0):
    """
    Save a :class:`~fenics.XDMFFile` with name ``name`` of the 
    :class:`~fenics.Function` ``u`` to the ``xdmf`` directory specified by 
    ``self.out_dir``.
    
    If ``f`` is a :class:`~fenics.XDMFFile` object, save to this instead.

    If ``t`` is a float or an int, mark the file with the timestep ``t``.

    :param u:    the function to save
    :param name: the name of the .xdmf file to save
    :param f:    the file to save to
    :param t:    the timestep to mark the file with
    :type f:     :class:`~fenics.XDMFFile`
    :type u:     :class:`~fenics.Function` or :class:`~fenics.GenericVector`
    :type t:     int or float
    """
    if f != None:
      s       = "::: saving %s.xdmf file :::" % name
      print_text(s, 'green')#cls=self.this)
      f << (u, float(t))
    else :
      s       = "::: saving %sxdmf/%s.xdmf file :::" % (self.out_dir, name)
      print_text(s, 'green')#cls=self.this)
      f = XDMFFile(self.out_dir + 'xdmf/' +  name + '.xdmf')
      f.write(u)

  def save_matlab(self, u, di, filename, val=np.e):
    """
    Create Matlab version 4 file output of regular gridded data contained by 
    ``f``.  Currently, this function only works for 2D :math:`x,y`-plane data.

    :param u:  a :class:`~fenics.Function`, to be mapped onto the regular 
               grid used by ``di``
    :param di: a :class:`~inputoutput.DataInput` object
    :param filename: filename to save as
    :param val:      value to make values outside of mesh, default :math:`e`
    :type u:         :class:`~fenics.Function` or :class:`~fenics.GenericVector`
    :type filename:  string
    :type val:       float
    :rtype:          MatLab file ``<self.out_dir>/matlab/<filename>.mat``.
    """
    fa   = zeros( (di.ny, di.nx) )
    s    = "::: writing %i x %i matlab matrix file %s.mat :::"
    text = s % (di.ny, di.nx, filename)
    print_text(text, cls=self.this)
    parameters['allow_extrapolation'] = True
    dim = f.geometric_dimension()
    for j,x in enumerate(di.x):
      for i,y in enumerate(di.y):
        try:
          fa[i,j] = f(x,y)
        except:
          fa[i,j] = val
    print_min_max(fa, filename + 'matrix')
    outfile = self.out_dir + 'matlab/' + filename + '.mat'
    savemat(outfile, {'map_data'          : fa,
                      'continent'         : di.cont,
                      'nx'                : di.nx,
                      'ny'                : di.ny,
                      'map_eastern_edge'  : di.x_max,
                      'map_western_edge'  : di.x_min,
                      'map_northern_edge' : di.y_max,
                      'map_southern_edge' : di.y_min,
                      'map_name'          : outfile,
                      'projection'        : di.proj.srs})
    
  def save_list_to_hdf5(self, lst, h5File):
    """
    save a list of functions or coefficients ``lst`` to hdf5 file ``h5File``.

    :param lst:    list
    :param h5File: the file to save to
    :type h5File:  :class:`~fenics.HDF5File`
    """
    s    = '::: saving variables in list arg post_tmc_save_vars :::'
    print_text(s, cls=self.this)
    for var in lst:
      self.save_hdf5(var, f=h5File)

  def save_subdomain_data(self, h5File):
    """
    Save the subdomain ``self.ff``, ``self.ff_acc``, and ``self.cf`` 
    to hd5f file ``h5File``.

    :param h5File: the file to save to
    :type h5File: :class:`~fenics.HDF5File`
    """
    s = "::: writing 'ff' FacetFunction to supplied hdf5 file :::"
    print_text(s, cls=self)
    h5File.write(self.ff,     'ff')

    s = "::: writing 'ff_acc' FacetFunction to supplied hdf5 file :::"
    print_text(s, cls=self)
    h5File.write(self.ff_acc, 'ff_acc')

    s = "::: writing 'cf' CellFunction to supplied hdf5 file :::"
    print_text(s, cls=self)
    h5File.write(self.cf,     'cf')

  def save_mesh(self, h5File): 
    """
    save the mesh ``self.mesh`` to :class:`~fenics.HDF5File` ``h5File``.
    
    :param h5File: the file to save to
    :type h5File:  :class:`~fenics.HDF5File`
    """
    s = "::: writing 'mesh' to supplied hdf5 file :::"
    print_text(s, cls=self.this)
    h5File.write(self.mesh, 'mesh')
  
  def solve_hydrostatic_pressure(self, annotate=False):
    r"""
    Solve for the hydrostatic pressure :math:`p = f_c = \rho g (S - z)` to 
    ``self.p``, with surface height :math:`S` given by ``self.S``, ice 
    density :math:`\rho` given by ``self.rho``, and :math:`z`-coordinate
    given by ``self.x[2]``.

    :param annotate: allow Dolfin-Adjoint annotation of this procedure.
    :type annotate: bool
    """
    raiseNotDefined()
  
  def initialize_variables(self):
    """
    Initialize the model variables to default values.  The variables 
    defined here are:
    
    Coordinates of various types : 

    * ``self.x``   -- :class:`~fenics.SpatialCoordinate` for ``self.mesh``
    * ``self.h``   -- :class:`~fenics.CellSize` for ``self.mesh``
    * ``self.N``   -- :class:`~fenics.FacetNormal` for ``self.mesh``
    * ``self.lat`` -- latitude :class:`~fenics.Function`
    * ``self.lon`` -- longitude :class:`~fenics.Function`
    * ``self.n_f`` -- outward-pointing normal :class:`~fenics.Function`

    Time step :

    * ``self.time_step`` -- the time step for transients

    Masks : 

    * ``self.mask``      -- shelf mask (1 if grounded, 2 if shelf)
    * ``self.lat_mask``  -- lateral boundary mask (1 if on lateral boundary)
    * ``self.U_mask``    -- velocity mask (1 if velocity measurements present)

    Topography :
    
    * ``self.S``         -- atmospheric surface 
    * ``self.B``         -- basal surface
    
    Velocity observations :
    
    * ``self.U_ob``      -- observed horizontal velocity vector
    * ``self.u_ob``      -- :math:`x`-compoenent of observed velocity
    * ``self.v_ob``      -- :math:`y`-compoenent of observed velocity
    
    Modeled velocity :
    
    * ``self.U_mag``     -- velocity vector magnitude
    * ``self.U3``        -- velocity vector
    * ``self.u``         -- :math:`x`-component of velocity vector
    * ``self.v``         -- :math:`y`-component of velocity vector
    * ``self.w``         -- :math:`z`-component of velocity vector

    Momentum :
    
    * ``self.eta``       -- viscosity
    * ``self.p``         -- pressure
    * ``self.beta``      -- basal traction
    * ``self.E``         -- enhancement factor
    * ``self.A``         -- flow-rate factor
    * ``self.u_lat``     -- :math:`x`-component velocity lateral b.c.
    * ``self.v_lat``     -- :math:`y`-component velocity lateral b.c.
    * ``self.w_lat``     -- :math:`z`-component velocity lateral b.c.
    
    Energy :
    
    * ``self.T``         -- temperature
    * ``self.Tp``        -- pressure-adjusted temperature
    * ``self.q_geo``     -- geothermal heat flux
    * ``self.q_fric``    -- frictional heat flux
    * ``self.gradT_B``   -- temperature gradient at the bed
    * ``self.gradTm_B``  -- temperature-melting gradient at the bed
    * ``self.theta``     -- internal energy
    * ``self.W``         -- water content
    * ``self.Wc``        -- maximum allowed water content
    * ``self.Mb``        -- basal-melt rate 
    * ``self.rhob``      -- bulk density
    * ``self.T_melt``    -- temperature melting point
    * ``self.theta_melt``-- energy melting point
    * ``self.T_surface`` -- surface temperature b.c.
    * ``self.alpha``     -- temperate zone marker
    * ``self.alpha_int`` -- vertically integrated temperate zone marker
    * ``self.Fb``        -- basal-water discharge
    * ``self.PE``        -- grid Peclet number
    * ``self.Wbar``      -- vertical average of water content
    * ``self.Fb_min``    -- lower bound on ``self.Fb``
    * ``self.Fb_max``    -- upper bound on ``self.Fb``
    * ``self.Qbar``      -- vertically-integrated strain heat
    * ``self.temp_rat``  -- ratio of column that is temperate
    * ``self.k_0``       -- non-advective water-flux coefficient
    
    Adjoint :
    
    * ``self.control_opt`` -- control parameter for momentum optimization

    Balance Velocity :
    
    * ``self.adot``      -- accumulation/ablation function 
    * ``self.d_x``       -- :math:`x`-component of flow direction
    * ``self.d_y``       -- :math:`y`-component of flow direction
    * ``self.Ubar``      -- balance velocity magnitude 
    * ``self.uhat``      -- :math:`x`-component of normalized flow direction
    * ``self.vhat``      -- :math:`y`-component of normalized flow direction 
    
    Stress-balance :
    
    * ``self.M_ii``      -- membrane-stress balance :math:`M_{ii}`
    * ``self.M_ij``      -- membrane-stress balance :math:`M_{ij}`
    * ``self.M_iz``      -- membrane-stress balance :math:`M_{iz}`
    * ``self.M_ji``      -- membrane-stress balance :math:`M_{ji}`
    * ``self.M_jj``      -- membrane-stress balance :math:`M_{jj}`
    * ``self.M_jz``      -- membrane-stress balance :math:`M_{jz}`
    * ``self.M_zi``      -- membrane-stress balance :math:`M_{zi}`
    * ``self.M_zj``      -- membrane-stress balance :math:`M_{zj}`
    * ``self.M_zz``      -- membrane-stress balance :math:`M_{zz}`
    * ``self.N_ii``      -- membrane-stress :math:`N_{ii}`
    * ``self.N_ij``      -- membrane-stress :math:`N_{ij}`
    * ``self.N_iz``      -- membrane-stress :math:`N_{iz}`
    * ``self.N_ji``      -- membrane-stress :math:`N_{ji}`
    * ``self.N_jj``      -- membrane-stress :math:`N_{jj}`
    * ``self.N_jz``      -- membrane-stress :math:`N_{jz}`
    * ``self.N_zi``      -- membrane-stress :math:`N_{zi}`
    * ``self.N_zj``      -- membrane-stress :math:`N_{zj}`
    * ``self.N_zz``      -- membrane-stress :math:`N_{zz}`
    """
    s = "::: initializing basic variables :::"
    print_text(s, cls=self.this)

    # Coordinates of various types 
    self.x             = SpatialCoordinate(self.mesh)
    self.h             = CellSize(self.mesh)
    self.N             = FacetNormal(self.mesh)
    self.lat           = Function(self.Q, name='lat')
    self.lon           = Function(self.Q, name='lon')
    self.n_f           = Function(self.V, name='n_f')

    # time step :
    self.time_step = Constant(100.0)
    self.time_step.rename('time_step', 'time step')

    # shelf mask (2 if shelf) :
    self.mask          = Function(self.Q, name='mask')

    # lateral boundary mask (1 if on lateral boundary) :
    self.lat_mask      = Function(self.Q, name='lat_mask')

    # velocity mask (1 if velocity measurements present) :
    self.U_mask        = Function(self.Q, name='U_mask')

    # topography :
    self.S             = Function(self.Q_non_periodic, name='S')
    self.B             = Function(self.Q_non_periodic, name='B')
    self.B_err         = Function(self.Q_non_periodic, name='B_err')
    
    # velocity observations :
    self.U_ob          = Function(self.Q, name='U_ob')
    self.u_ob          = Function(self.Q, name='u_ob')
    self.v_ob          = Function(self.Q, name='v_ob')
    
    # unified velocity (non-periodic because it is always known everywhere) :
    self.U_mag         = Function(self.Q,               name='U_mag')
    self.U3            = Function(self.Q3_non_periodic, name='U3')
    u,v,w              = self.U3.split()
    u.rename('u', '')
    v.rename('v', '')
    w.rename('w', '')
    self.u             = u
    self.v             = v
    self.w             = w
    self.assx  = FunctionAssigner(u.function_space(), self.Q_non_periodic)
    self.assy  = FunctionAssigner(v.function_space(), self.Q_non_periodic)
    self.assz  = FunctionAssigner(w.function_space(), self.Q_non_periodic)

    # momentum model :
    self.eta           = Function(self.Q, name='eta')
    self.p             = Function(self.Q_non_periodic, name='p')
    self.beta          = Function(self.Q, name='beta')
    self.E             = Function(self.Q, name='E')
    self.A             = Function(self.Q, name='A')
    self.u_lat         = Function(self.Q, name='u_lat')
    self.v_lat         = Function(self.Q, name='v_lat')
    self.w_lat         = Function(self.Q, name='w_lat')
    self.lam           = Function(self.Q, name='lam')
    
    # energy model :
    self.T             = Function(self.Q, name='T')
    self.Tp            = Function(self.Q, name='Tp')
    self.q_geo         = Function(self.Q, name='q_geo')
    self.q_fric        = Function(self.Q, name='q_fric')
    self.gradT_B       = Function(self.Q, name='gradT_B')
    self.gradTm_B      = Function(self.Q, name='gradTm_B')
    self.theta         = Function(self.Q, name='theta')
    self.W             = Function(self.Q, name='W')
    self.W0            = Function(self.Q, name='W0')
    self.Wc            = Function(self.Q, name='Wc')
    self.Mb            = Function(self.Q, name='Mb')
    self.rhob          = Function(self.Q, name='rhob')
    self.T_melt        = Function(self.Q, name='T_melt')     # pressure-melting
    self.theta_melt    = Function(self.Q, name='theta_melt') # pressure-melting
    self.T_surface     = Function(self.Q, name='T_surface')
    self.theta_surface = Function(self.Q, name='theta_surface')
    self.theta_float   = Function(self.Q, name='theta_float')
    self.theta_app     = Function(self.Q, name='theta_app')
    self.alpha         = Function(self.Q, name='alpha')
    self.alpha_int     = Function(self.Q, name='alpha_int')
    self.Fb            = Function(self.Q, name='Fb')
    self.PE            = Function(self.Q, name='PE')
    self.Wbar          = Function(self.Q, name='Wbar')
    self.Fb_min        = Function(self.Q, name='Fb_min')
    self.Fb_max        = Function(self.Q, name='Fb_max')
    self.Qbar          = Function(self.Q, name='Qbar')
    self.temp_rat      = Function(self.Q, name='temp_rat')
    self.k_0           = Constant(1.0,    name='k_0')
    self.k_0.rename('k_0', 'k_0')
    
    # adjoint model :
    self.control_opt   = Function(self.Q, name='control_opt')

    # balance Velocity model :
    self.adot          = Function(self.Q, name='adot')
    self.d_x           = Function(self.Q, name='d_x')
    self.d_y           = Function(self.Q, name='d_y')
    self.Ubar          = Function(self.Q, name='Ubar')
    self.uhat          = Function(self.Q, name='uhat')
    self.vhat          = Function(self.Q, name='vhat')
    
    # Stress-balance model (this is always non-periodic) :
    self.M_ii          = Function(self.Q_non_periodic, name='M_ii')
    self.M_ij          = Function(self.Q_non_periodic, name='M_ij')
    self.M_iz          = Function(self.Q_non_periodic, name='M_iz')
    self.M_ji          = Function(self.Q_non_periodic, name='M_ji')
    self.M_jj          = Function(self.Q_non_periodic, name='M_jj')
    self.M_jz          = Function(self.Q_non_periodic, name='M_jz')
    self.M_zi          = Function(self.Q_non_periodic, name='M_zi')
    self.M_zj          = Function(self.Q_non_periodic, name='M_zj')
    self.M_zz          = Function(self.Q_non_periodic, name='M_zz')
    self.N_ii          = Function(self.Q_non_periodic, name='N_ii')
    self.N_ij          = Function(self.Q_non_periodic, name='N_ij')
    self.N_iz          = Function(self.Q_non_periodic, name='N_iz')
    self.N_ji          = Function(self.Q_non_periodic, name='N_ji')
    self.N_jj          = Function(self.Q_non_periodic, name='N_jj')
    self.N_jz          = Function(self.Q_non_periodic, name='N_jz')
    self.N_zi          = Function(self.Q_non_periodic, name='N_zi')
    self.N_zj          = Function(self.Q_non_periodic, name='N_zj')
    self.N_zz          = Function(self.Q_non_periodic, name='N_zz')

  def home_rolled_newton_method(self, R, U, J, bcs, atol=1e-7, rtol=1e-10,
                                relaxation_param=1.0, max_iter=25,
                                method='mumps', preconditioner='default',
                                cb_ftn=None, bp_Jac=None, bp_R=None):
    """
    Appy Newton's method.

    :param R:                residual of system
    :param U:                unknown to determine
    :param J:                Jacobian
    :param bcs:              set of Dirichlet boundary conditions
    :param atol:             absolute stopping tolerance
    :param rtol:             relative stopping tolerance
    :param relaxation_param: ratio of down-gradient step to take each iteration.
    :param max_iter:         maximum number of iterations to perform
    :param method:           linear solution method
    :param preconditioner:   preconditioning method to use with ``Krylov``
                             solver
    :param cb_ftn:           at the end of each iteration, this is called
    """
    converged  = False
    lmbda      = relaxation_param   # relaxation parameter
    nIter      = 0                  # number of iterations

    ## Set PETSc solve type (conjugate gradient) and preconditioner
    ## (algebraic multigrid)
    #PETScOptions.set("ksp_type", "cg")
    #PETScOptions.set("pc_type", "gamg")
    #
    ## Since we have a singular problem, use SVD solver on the multigrid
    ## 'coarse grid'
    #PETScOptions.set("mg_coarse_ksp_type", "preonly")
    #PETScOptions.set("mg_coarse_pc_type", "svd")
    #
    ## Set the solver tolerance
    #PETScOptions.set("ksp_rtol", 1.0e-8)
    #
    ## Print PETSc solver configuration
    #PETScOptions.set("ksp_view")
    #PETScOptions.set("ksp_monitor")
    
    #PETScOptions().set('ksp_type',                      method)
    #PETScOptions().set('mat_type',                      'matfree')
    #PETScOptions().set('pc_type',                       preconditioner)
    #PETScOptions().set('pc_factor_mat_solver_package',  'mumps')
    #PETScOptions().set('pc_fieldsplit_schur_fact_type', 'diag')
    #PETScOptions().set('pc_fieldsplit_type',            'schur')
    #PETScOptions().set('fieldsplit_0_ksp_type',         'preonly')
    #PETScOptions().set('fieldsplit_0_pc_type',          'python')
    #PETScOptions().set('fieldsplit_1_ksp_type',         'preonly')
    #PETScOptions().set('fieldsplit_1_pc_type',          'python')
    #PETScOptions().set('fieldsplit_1_Mp_ksp_type',      'preonly')
    #PETScOptions().set('fieldsplit_1_Mp_pc_type',       'ilu')
    #PETScOptions().set('assembled_pc_type',             'hypre')
   
    # need to homogenize the boundary, as the residual is always zero over
    # essential boundaries :
    bcs_u = []
    for bc in bcs:
      bc = DirichletBC(bc)
      bc.homogenize()
      bcs_u.append(bc)
    
    # the direction of decent :
    d = Function(U.function_space()) 
    
    while not converged and nIter < max_iter:
    
      # assemble system :
      A, b    = assemble_system(J, -R, bcs_u)
    
      ## Create Krylov solver and AMG preconditioner
      #solver  = PETScKrylovSolver(method)#, preconditioner)

      ## Assemble preconditioner system
      #P, btmp = assemble_system(bp_Jac, -bp_R)

      ### Associate operator (A) and preconditioner matrix (P)
      ##solver.set_operators(A, P)
      #solver.set_operator(A)

      ## Set PETSc options on the solver
      #solver.set_from_options()

      ## determine step direction :
      #solver.solve(d.vector(), b, annotate=False)

      # determine step direction :
      solve(A, d.vector(), b, method, preconditioner, annotate=False)
    
      # calculate residual :
      residual  = b.norm('l2')
    
      # set initial residual : 
      if nIter == 0:
        residual_0 = residual

      # the relative residual :
      rel_res = residual/residual_0

      # check for convergence :
      converged = residual < atol or rel_res < rtol
      
      # move U down the gradient :
      U.vector()[:] += lmbda*d.vector()
      
      # increment counter :
      nIter += 1
    
      # print info to screen :
      if self.MPI_rank == 0:
        string = "Newton iteration %d: r (abs) = %.3e (tol = %.3e) " \
                 +"r (rel) = %.3e (tol = %.3e)"
        print string % (nIter, residual, atol, rel_res, rtol)

      # call the callback function, if desired :
      if cb_ftn is not None:
        s    = "::: calling home-rolled Newton method callback :::"
        print_text(s, cls=self.this)
        cb_ftn()

  def thermo_solve(self, momentum, energy, wop_kwargs,
                   callback=None, atol=1e2, rtol=1e0, max_iter=50,
                   iter_save_vars=None, post_tmc_save_vars=None,
                   starting_i=1):
    r""" 
    Perform thermo-mechanical coupling between momentum and energy.

    :param momentum:       an :class:`~momentum.Momentum` instance
    :param energy:         an :class:`~energy.Energy` instance.  Currently 
                           this only works for :class:`~energy.Enthalpy`
    :param wop_kwargs:     a :py:class:`~dict` of arguments for
                           water-optimization method 
                           :func:`~energy.Energy.optimize_water_flux`
    :param callback:       a function that is called back at the end of each 
                           iteration
    :param atol:           absolute stopping tolerance 
                           :math:`a_{tol} \leq r = \Vert \theta_n - \theta_{n-1} \Vert`
    :param rtol:           relative stopping tolerance
                           :math:`r_{tol} \leq \Vert r_n - r_{n-1} \Vert`
    :param max_iter:       maximum number of iterations to perform
    :param iter_save_vars: python :py:class:`~list` containing functions to 
                           save each iteration
    :param starting_i:     if you are restarting this process, you may start 
                           it at a later iteration. 
    """
    s    = '::: performing thermo-mechanical coupling with atol = %.2e, ' + \
           'rtol = %.2e, and max_iter = %i :::'
    print_text(s % (atol, rtol, max_iter), cls=self.this)
    
    from cslvr import Momentum
    from cslvr import Energy
    
    if not isinstance(momentum, Momentum):
      s = ">>> thermo_solve REQUIRES A 'Momentum' INSTANCE, NOT %s <<<"
      print_text(s % type(momentum) , 'red', 1)
      sys.exit(1)
    
    if not isinstance(energy, Energy):
      s = ">>> thermo_solve REQUIRES AN 'Energy' INSTANCE, NOT %s <<<"
      print_text(s % type(energy) , 'red', 1)
      sys.exit(1)

    # mark starting time :
    t0   = time()

    # ensure that we have a steady-state form :
    if energy.transient:
      energy.make_steady_state()

    # retain base install directory :
    out_dir_i = self.out_dir

    # directory for saving convergence history :
    d_hist   = self.out_dir + 'tmc/convergence_history/'
    if not os.path.exists(d_hist) and self.MPI_rank == 0:
      os.makedirs(d_hist)

    # number of digits for saving variables :
    n_i  = len(str(max_iter))
    
    # get the bounds of Fb, the max will be updated based on temperate zones :
    if energy.energy_flux_mode == 'Fb':
      bounds = copy(wop_kwargs['bounds'])
      self.init_Fb_min(bounds[0])
      self.init_Fb_max(bounds[1])
      wop_kwargs['bounds']  = (self.Fb_min, self.Fb_max)

    # L_2 erro norm between iterations :
    abs_error = np.inf
    rel_error = np.inf
      
    # number of iterations, from a starting point (useful for restarts) :
    if starting_i <= 1:
      counter = 1
    else:
      counter = starting_i
   
    # previous velocity for norm calculation
    U_prev    = self.theta.copy(True)

    # perform a fixed-point iteration until the L_2 norm of error 
    # is less than tolerance :
    while abs_error > atol and rel_error > rtol and counter <= max_iter:
       
      # set a new unique output directory :
      out_dir_n = 'tmc/%0*d/' % (n_i, counter)
      self.set_out_dir(out_dir_i + out_dir_n)
      
      # solve velocity :
      momentum.solve(annotate=False)

      # update pressure-melting point :
      energy.calc_T_melt(annotate=False)

      # calculate basal friction heat flux :
      momentum.calc_q_fric()
      
      # derive temperature and temperature-melting flux terms :
      energy.calc_basal_temperature_flux()
      energy.calc_basal_temperature_melting_flux()

      # solve energy steady-state equations to derive temperate zone :
      energy.derive_temperate_zone(annotate=False)
      
      # fixed-point interation for thermal parameters and discontinuous 
      # properties :
      energy.update_thermal_parameters(annotate=False)
      
      # calculate the basal-melting rate :
      energy.solve_basal_melt_rate()
      
      # always initialize Fb to the zero-energy-flux bc :  
      Fb_v = self.Mb.vector().array() * self.rhoi(0) / self.rhow(0)
      self.init_Fb(Fb_v)
  
      # update bounds based on temperate zone :
      if energy.energy_flux_mode == 'Fb':
        Fb_m_v                 = self.Fb_max.vector().array()
        alpha_v                = self.alpha.vector().array()
        Fb_m_v[:]              = DOLFIN_EPS
        Fb_m_v[alpha_v == 1.0] = bounds[1]
        self.init_Fb_max(Fb_m_v)
      
      # optimize the flux of water to remove abnormally high water :
      if energy.energy_flux_mode == 'Fb':
        energy.optimize_water_flux(**wop_kwargs)

      # solve the energy-balance and partition T and W from theta :
      energy.solve(annotate=False)
      
      # calculate L_2 norms :
      abs_error_n  = norm(U_prev.vector() - self.theta.vector(), 'l2')
      tht_nrm      = norm(self.theta.vector(), 'l2')

      # save convergence history :
      if counter == 1:
        rel_error  = abs_error_n
        if self.MPI_rank == 0:
          err_a = np.array([abs_error_n])
          nrm_a = np.array([tht_nrm])
          np.savetxt(d_hist + 'abs_err.txt',    err_a)
          np.savetxt(d_hist + 'theta_norm.txt', nrm_a)
      else:
        rel_error = abs(abs_error - abs_error_n)
        if self.MPI_rank == 0:
          err_n = np.loadtxt(d_hist + 'abs_err.txt')
          nrm_n = np.loadtxt(d_hist + 'theta_norm.txt')
          err_a = np.append(err_n, np.array([abs_error_n]))
          nrm_a = np.append(nrm_n, np.array([tht_nrm]))
          np.savetxt(d_hist + 'abs_err.txt',     err_a)
          np.savetxt(d_hist + 'theta_norm.txt',  nrm_a)

      # print info to screen :
      if self.MPI_rank == 0:
        s0    = '>>> '
        s1    = 'TMC fixed-point iteration %i (max %i) done: ' \
                 % (counter, max_iter)
        s2    = 'r (abs) = %.2e ' % abs_error
        s3    = '(tol %.2e), '    % atol
        s4    = 'r (rel) = %.2e ' % rel_error
        s5    = '(tol %.2e)'      % rtol
        s6    = ' <<<'
        text0 = get_text(s0, 'red', 1)
        text1 = get_text(s1, 'red')
        text2 = get_text(s2, 'red', 1)
        text3 = get_text(s3, 'red')
        text4 = get_text(s4, 'red', 1)
        text5 = get_text(s5, 'red')
        text6 = get_text(s6, 'red', 1)
        print text0 + text1 + text2 + text3 + text4 + text5 + text6
      
      # update error stuff and increment iteration counter :
      abs_error    = abs_error_n
      U_prev       = self.theta.copy(True)
      counter     += 1

      # call callback function if set :
      if callback != None:
        s    = '::: calling thermo-couple-callback function :::'
        print_text(s, cls=self.this)
        callback()
    
      # save state to unique hdf5 file :
      if isinstance(iter_save_vars, list):
        s    = '::: saving variables in list arg iter_save_vars :::'
        print_text(s, cls=self.this)
        out_file = self.out_dir + 'tmc.h5'
        foutput  = HDF5File(mpi_comm_world(), out_file, 'w')
        for var in iter_save_vars:
          self.save_hdf5(var, f=foutput)
        foutput.close()
    
    # reset the base directory ! :
    self.set_out_dir(out_dir_i)
    
    # reset the bounds on Fb :
    if energy.energy_flux_mode == 'Fb':  wop_kwargs['bounds'] = bounds
      
    # save state to unique hdf5 file :
    if isinstance(post_tmc_save_vars, list):
      s    = '::: saving variables in list arg post_tmc_save_vars :::'
      print_text(s, cls=self.this)
      out_file = self.out_dir + 'tmc.h5'
      foutput  = HDF5File(mpi_comm_world(), out_file, 'w')
      for var in post_tmc_save_vars:
        self.save_hdf5(var, f=foutput)
      foutput.close()

    # calculate total time to compute
    tf = time()
    s  = tf - t0
    m  = s / 60.0
    h  = m / 60.0
    s  = s % 60
    m  = m % 60
    text = "time to thermo-couple: %02d:%02d:%02d" % (h,m,s)
    print_text(text, 'red', 1)
       
    # plot the convergence history : 
    s    = "::: convergence info saved to \'%s\' :::"
    print_text(s % d_hist, cls=self.this)
    if self.MPI_rank == 0:
      np.savetxt(d_hist + 'time.txt', np.array([tf - t0]))

      err_a = np.loadtxt(d_hist + 'abs_err.txt')
      nrm_a = np.loadtxt(d_hist + 'theta_norm.txt')
     
      # plot iteration error : 
      fig   = plt.figure()
      ax    = fig.add_subplot(111)
      ax.set_ylabel(r'$\Vert \theta_{n-1} - \theta_n \Vert$')
      ax.set_xlabel(r'iteration')
      ax.plot(err_a, 'k-', lw=2.0)
      plt.grid()
      plt.savefig(d_hist + 'abs_err.png', dpi=100)
      plt.close(fig)
      
      # plot theta norm :
      fig = plt.figure()
      ax  = fig.add_subplot(111)
      ax.set_ylabel(r'$\Vert \theta_n \Vert$')
      ax.set_xlabel(r'iteration')
      ax.plot(nrm_a, 'k-', lw=2.0)
      plt.grid()
      plt.savefig(d_hist + 'theta_norm.png', dpi=100)
      plt.close(fig)

  def assimilate_U_ob(self, momentum, beta_i, max_iter, 
                      tmc_kwargs, uop_kwargs,
                      atol                = 1e2,
                      rtol                = 1e0, 
                      initialize          = True,
                      incomplete          = True,
                      post_iter_save_vars = None,
                      post_ini_callback   = None,
                      starting_i          = 1):
    """
    """
    s    = '::: performing assimilation process with %i max iterations :::'
    print_text(s % max_iter, cls=self.this)

    # retain base install directory :
    out_dir_i = self.out_dir
    
    # directory for saving convergence history :
    d_hist   = self.out_dir + 'convergence_history/'
    if not os.path.exists(d_hist) and self.MPI_rank == 0:
      os.makedirs(d_hist)

    # number of digits for saving variables :
    n_i  = len(str(max_iter))
    
    # starting time :
    t0   = time()
    
    # L_2 erro norm between iterations :
    abs_error = np.inf
    rel_error = np.inf
      
    # number of iterations, from a starting point (useful for restarts) :
    if starting_i <= 1:
      counter = 1
    else:
      counter = starting_i

    # initialize friction field :
    self.init_beta(beta_i)
   
    # previous friction for norm calculation :
    beta_prev    = self.beta.copy(True)

    # perform initialization step if desired :
    if initialize:
      s    = '    - performing initialization step -'
      print_text(s, cls=self.this)

      # set the initialization output directory :
      out_dir_n = 'initialization/'
      self.set_out_dir(out_dir_i + out_dir_n)
      
      # thermo-mechanical couple :
      self.thermo_solve(**tmc_kwargs)

      # call the post function if set :
      if post_ini_callback is not None:
        s    = '::: calling post-initialization assimilate_U_ob ' + \
               'callback function :::'
        print_text(s, cls=self.this)
        post_ini_callback()

    # otherwise, tell us that we are not initializing :
    else:
      s    = '    - skipping initialization step -'
      print_text(s, cls=self.this)
    
    # save the w_opt bounds on Fb :
    bounds = copy(tmc_kwargs['wop_kwargs']['bounds'])

    # assimilate the data : 
    while abs_error > atol and rel_error > rtol and counter <= max_iter:
      s    = '::: entering iterate %i of %i of assimilation process :::'
      print_text(s % (counter, max_iter), cls=self.this)
       
      # set a new unique output directory :
      out_dir_n = '%0*d/' % (n_i, counter)
      self.set_out_dir(out_dir_i + out_dir_n)
   
      # the incomplete adjoint means the viscosity is linear, and
      # we do not want to reset the original momentum configuration, because
      # we have more non-linear solves to do :
      if incomplete and not momentum.linear:
        momentum.linearize_viscosity(reset_orig_config=True)
    
      # re-initialize friction field :
      if counter > starting_i: self.init_beta(beta_i)

      # optimize the velocity : 
      momentum.optimize_U_ob(**uop_kwargs)

      # reset the momentum to the original configuration : 
      if not momentum.linear_s and momentum.linear: momentum.reset()

      # thermo-mechanically couple :
      self.thermo_solve(**tmc_kwargs)
      
      # calculate L_2 norms :
      abs_error_n  = norm(beta_prev.vector() - self.beta.vector(), 'l2')
      beta_nrm     = norm(self.beta.vector(), 'l2')

      # save convergence history :
      if counter == 1:
        rel_error  = abs_error_n
        if self.MPI_rank == 0:
          err_a = np.array([abs_error_n])
          nrm_a = np.array([beta_nrm])
          np.savetxt(d_hist + 'abs_err.txt',   err_a)
          np.savetxt(d_hist + 'beta_norm.txt', nrm_a)
      else:
        rel_error = abs(abs_error - abs_error_n)
        if self.MPI_rank == 0:
          err_n = np.loadtxt(d_hist + 'abs_err.txt')
          nrm_n = np.loadtxt(d_hist + 'beta_norm.txt')
          err_a = np.append(err_n, np.array([abs_error_n]))
          nrm_a = np.append(nrm_n, np.array([beta_nrm]))
          np.savetxt(d_hist + 'abs_err.txt',    err_a)
          np.savetxt(d_hist + 'beta_norm.txt',  nrm_a)

      # print info to screen :
      if self.MPI_rank == 0:
        s0    = '>>> '
        s1    = 'U_ob assimilation iteration %i (max %i) done: ' \
                % (counter, max_iter)
        s2    = 'r (abs) = %.2e ' % abs_error
        s3    = '(tol %.2e), '    % atol
        s4    = 'r (rel) = %.2e ' % rel_error
        s5    = '(tol %.2e)'      % rtol
        s6    = ' <<<'
        text0 = get_text(s0, 'red', 1)
        text1 = get_text(s1, 'red')
        text2 = get_text(s2, 'red', 1)
        text3 = get_text(s3, 'red')
        text4 = get_text(s4, 'red', 1)
        text5 = get_text(s5, 'red')
        text6 = get_text(s6, 'red', 1)
        print text0 + text1 + text2 + text3 + text4 + text5 + text6
      
      # save state to unique hdf5 file :
      if isinstance(post_iter_save_vars, list):
        s    = '::: saving variables in list arg post_iter_save_vars :::'
        print_text(s, cls=self.this)
        out_file = self.out_dir + 'inverted.h5'
        foutput  = HDF5File(mpi_comm_world(), out_file, 'w')
        for var in post_iter_save_vars:
          self.save_hdf5(var, f=foutput)
        foutput.close()
      
      # update error stuff and increment iteration counter :
      abs_error    = abs_error_n
      beta_prev    = self.beta.copy(True)
      counter     += 1

    # calculate total time to compute
    tf = time()
    s  = tf - t0
    m  = s / 60.0
    h  = m / 60.0
    s  = s % 60
    m  = m % 60
    text = "time to compute TMC optimized ||u - u_ob||: %02d:%02d:%02d"
    print_text(text % (h,m,s) , 'red', 1)
       
    # plot the convergence history : 
    s    = "::: convergence info saved to \'%s\' :::"
    print_text(s % d_hist, cls=self.this)
    if self.MPI_rank == 0:
      np.savetxt(d_hist + 'time.txt', np.array([tf - t0]))

      err_a = np.loadtxt(d_hist + 'abs_err.txt')
      nrm_a = np.loadtxt(d_hist + 'beta_norm.txt')
     
      # plot iteration error : 
      fig   = plt.figure()
      ax    = fig.add_subplot(111)
      ax.set_ylabel(r'$\Vert \beta_{n-1} - \beta_n \Vert$')
      ax.set_xlabel(r'iteration')
      ax.plot(err_a, 'k-', lw=2.0)
      plt.grid()
      plt.savefig(d_hist + 'abs_err.png', dpi=100)
      plt.close(fig)
      
      # plot theta norm :
      fig = plt.figure()
      ax  = fig.add_subplot(111)
      ax.set_ylabel(r'$\Vert \beta_n \Vert$')
      ax.set_xlabel(r'iteration')
      ax.plot(nrm_a, 'k-', lw=2.0)
      plt.grid()
      plt.savefig(d_hist + 'beta_norm.png', dpi=100)
      plt.close(fig)

  def L_curve(self, alphas, control, physics, J, R, adj_kwargs, 
              pre_callback  = None,
              post_callback = None,
              itr_save_vars = None):
    """
    """
    s    = '::: starting L-curve procedure :::'
    print_text(s, cls=self.this)
    
    # starting time :
    t0   = time()

    # retain base install directory :
    out_dir_i = self.out_dir

    # retain initial control parameter for consistency :
    control_ini = control.copy(True)

    # iterate through each of the regularization parameters provided : 
    for i,alpha in enumerate(alphas):
      s    = '::: performing L-curve iteration %i with alpha = %.3e :::'
      print_text(s % (i,alpha) , atrb=1, cls=self.this)

      # reset everything after the first iteration :
      if i > 0:
        s    = '::: initializing physics :::'
        print_text(s, cls=self.this)
        physics.reset()
        self.assign_variable(control, control_ini)
      
      # set the appropriate output directory :
      out_dir_n = 'alpha_%.1E/' % alpha
      self.set_out_dir(out_dir_i + out_dir_n)
      
      # call the pre-adjoint callback function :
      if pre_callback is not None:
        s    = '::: calling L_curve() pre-adjoint pre_callback() :::'
        print_text(s, cls=self.this)
        pre_callback()

      # form new objective functional :
      adj_kwargs['I'] = J + alpha*R
     
      # solve the adjoint system :
      physics.optimize(**adj_kwargs)
      
      # call the pre-adjoint callback function :
      if post_callback is not None:
        s    = '::: calling L_curve() post-adjoint post_callback() :::'
        print_text(s, cls=self.this)
        post_callback()
      
      # save state to unique hdf5 file :
      if isinstance(itr_save_vars, list):
        s    = '::: saving variables in list arg itr_save_vars :::'
        print_text(s, cls=self.this)
        out_file = self.out_dir + 'lcurve.h5'
        foutput  = HDF5File(mpi_comm_world(), out_file, 'w')
        for var in itr_save_vars:
          self.save_hdf5(var, f=foutput)
        foutput.close()
    
    s    = '::: L-curve procedure complete :::'
    print_text(s, cls=self.this)

    # calculate total time to compute
    s = time() - t0
    m = s / 60.0
    h = m / 60.0
    s = s % 60
    m = m % 60
    text = "time to complete L-curve procedure: %02d:%02d:%02d" % (h,m,s)
    print_text(text, 'red', 1)

    #===========================================================================
   
    # save the resulting functional values and alphas to CSF : 
    if self.MPI_rank==0:

      # iterate through the directiories we just created and grab the data :
      alphas = []
      J_logs = []
      J_l2s  = []
      J_rats = []
      J_abss = []
      R_tvs  = []
      R_tiks = []
      R_sqs  = []
      R_abss = []
      ns     = []
      for d in next(os.walk(out_dir_i))[1]:
        m = re.search('(alpha_)(\d\W\dE\W\d+)', d)
        if m is not None:
          do = out_dir_i + d + '/objective_ftnls_history/'
          alphas.append(float(m.group(2)))
          J_logs.append( np.loadtxt(do  + 'J_log.txt'))
          J_l2s.append(  np.loadtxt(do  + 'J_l2.txt'))
          J_rats.append( np.loadtxt(do  + 'J_rat.txt'))
          J_abss.append( np.loadtxt(do  + 'J_abs.txt'))
          R_tvs.append(  np.loadtxt(do  + 'R_tv_%s.txt'  % control.name()))
          R_tiks.append( np.loadtxt(do  + 'R_tik_%s.txt' % control.name()))
          R_sqs.append(  np.loadtxt(do  + 'R_sq_%s.txt'  % control.name()))
          R_abss.append( np.loadtxt(do  + 'R_abs_%s.txt' % control.name()))
          ns.append(len(J_logs[-1]))
      alphas = np.array(alphas) 
      J_logs = np.array(J_logs)
      J_l2s  = np.array(J_l2s)
      J_rats = np.array(J_rats)
      J_abss = np.array(J_abss)
      R_tvs  = np.array(R_tvs)
      R_tiks = np.array(R_tiks)
      R_sqs  = np.array(R_sqs)
      R_abss = np.array(R_abss)
      ns     = np.array(ns)

      # sort everything :
      idx    = np.argsort(alphas)
      alphas = alphas[idx]
      J_logs = J_logs[idx] 
      J_l2s  = J_l2s[idx]
      J_rats = J_rats[idx]
      J_abss = J_abss[idx]
      R_tvs  = R_tvs[idx]
      R_tiks = R_tiks[idx]
      R_sqs  = R_sqs[idx]
      R_abss = R_abss[idx]
      ns     = ns[idx]
     
      # plot the functionals : 
      #=========================================================================
      fig = plt.figure(figsize=(6,2.5))
      ax  = fig.add_subplot(111)

      # we want to plot the different alpha values a different shade :
      cmap = plt.get_cmap('viridis')
      colors = [ cmap(x) for x in np.linspace(0, 1, 8) ]
    
      # the subscripts of file names :
      subs = ['log', 'l2',  'rat', 'abs', 'tv',  'tik', 'sq',  'abs']
    
      # the functional type
      ftnl_t = ['J', 'J', 'J', 'J', 'R', 'R', 'R', 'R']

      # collect the cost functionals :
      ftnl_a = [J_logs, J_l2s,  J_rats, J_abss, R_tvs,  R_tiks, R_sqs,  R_abss]
      
      k    = 0    # counter so we can plot side-by-side
      ints = [0]  # to modify the x-axis labels
      for i in range(len(alphas)):
        
        # create the x-interval to plot :
        xi = np.arange(k, k + ns[i])
        ints.append(xi.max())

        # if this is the first iteration, we put a legend on it :
        if i == 0:
          for ft, nm, sub, c in zip(ftnl_a, ftnl_t, subs, colors):
            ax.plot(xi, ft[i],  '-',  c=c,  lw=1.5, alpha=0.8,
                    label = r'$\mathscr{%s}_{\mathrm{%s}}$' % (nm, sub))

        # otherwise, we don't need cluttered legends :
        else:
          for ft, c in zip(ftnl_a, colors):
            ax.plot(xi, ft[i],  '-',  c=c,  lw=1.5, alpha=0.8,)

        k += ns[i] - 1

      ints = np.array(ints)
      
      label = []
      for i in alphas:
        label.append(r'$\gamma = %g$' % i)

      # reset the x-label to be meaningfull :
      ax.set_xticks(ints)
      ax.set_xticklabels(label, size='small', ha='left')#, rotation=-45)
      ax.set_xlabel(r'relative iteration')
      ax.set_xlim([0, ints[-1]])
      
      ax.xaxis.grid()
      ax.set_yscale('log')
      
      # plot the functional legend across the top in a row : 
      #leg = ax.legend(loc='upper center', ncol=4)
      #leg = ax.legend(loc='center right')
      leg = ax.legend(bbox_to_anchor=(1.2,0.5), loc='center right', ncol=1)
      leg.get_frame().set_alpha(0.0)
      leg.get_frame().set_color('w')
      
      plt.tight_layout(rect=[0.005,0.01,0.88,0.995])
      plt.savefig(out_dir_i + 'convergence.pdf')
      plt.close(fig)

      # plot L-curve :
      #=========================================================================
      
      colors    = [cmap(x) for x in np.linspace(0,1,len(alphas))]
      fig, ax_a = plt.subplots(4,4, figsize=(10,10))
      J_lbl     = r'$\mathscr{J}_{\mathrm{%s}}$'
      R_lbl     = r'$\mathscr{R}_{\mathrm{%s}}$'
      
      for i in range(4):
        J_i   = ftnl_a[i][:,-1]
        for j in range(4):
          R_j   = ftnl_a[4+j][:,-1]
          ax_a[i,j].plot(J_i, R_j, '-', c='k', lw=1.5)
          for k in range(len(alphas)):
            ax_a[i,j].plot(J_i[k], R_j[k], 'o', c=colors[k], lw=2.0,
                           label = r'$\gamma = %g$' % alphas[k])
          tit = r'%s $\circ$ %s' % (R_lbl % subs[4+j], J_lbl % subs[i])
          ax_a[i,j].set_title(tit)
          #ax_a[i,j].set_xlabel(J_lbl % subs[i])
          #ax_a[i,j].set_ylabel(R_lbl % subs[4+j])
          #ax_a[i,j].grid()
          ax_a[i,j].set_yscale('log')
          ##ax_a[i,j].set_xscale('log')
          if i == 0 and j == 0:
            leg = ax_a[i,j].legend(loc='upper right', ncol=2)
            leg.get_frame().set_alpha(0.0)

      # we only want the last value of each optimization : 
      #fin_Js = Js[:,-1]
      #fin_Rs = Rs[:,-1]
      
      #fig = plt.figure(figsize=(6,2.5))
      #ax  = fig.add_subplot(111)
      
      #ax.plot(fin_Js, fin_Rs, 'k-', lw=2.0)
      
      ax.grid()
    
      ## useful for figuring out what reg. parameter goes with what :  
      #for i,c in zip(range(len(alphas)), colors):
      #  ax.plot(fin_Js[i], fin_Rs[i], 'o',  c=c, lw=2.0,
      #          label = r'$\gamma = %g$' % alphas[i])
     
      #ax.set_xlabel(r'$\mathscr{I}^*$')
      #ax.set_ylabel(r'$\mathscr{R}^*$')
      
      #leg = ax.legend(loc='upper right', ncol=2)
      #leg.get_frame().set_alpha(0.0)
      
      #ax.set_yscale('log')
      ##ax.set_xscale('log')
      
      plt.tight_layout()
      plt.savefig(out_dir_i + 'l_curve.pdf')
      plt.close(fig)

      # save the functionals :
      #=========================================================================

      #d = out_dir_i + 'functionals/'
      #if not os.path.exists(d):
      #  os.makedirs(d)
      #np.savetxt(d + 'Rs.txt',   np.array(fin_Rs))
      #np.savetxt(d + 'Js.txt',   np.array(fin_Js))
      #np.savetxt(d + 'as.txt',   np.array(alphas))

  def transient_solve(self, momentum, energy, mass, t_start, t_end, time_step,
                      adaptive=False, annotate=False, callback=None):
    """
    """
    s    = '::: performing transient run :::'
    print_text(s, cls=self)
    
    from cslvr.momentum import Momentum
    from cslvr.energy   import Energy
    from cslvr.mass     import Mass
    
    if momentum.__class__.__base__ != Momentum:
      s = ">>> transient_solve REQUIRES A 'Momentum' INSTANCE, NOT %s <<<"
      print_text(s % type(momentum), 'red', 1)
      sys.exit(1)
    
    if energy.__class__.__base__ != Energy:
      s = ">>> transient_solve REQUIRES AN 'Energy' INSTANCE, NOT %s <<<"
      print_text(s % type(energy), 'red', 1)
      sys.exit(1)
    
    if mass.__class__.__base__ != Mass:
      s = ">>> transient_solve REQUIRES A 'Mass' INSTANCE, NOT %s <<<"
      print_text(s % type(mass), 'red', 1)
      sys.exit(1)
    
    stars = "*****************************************************************"
    self.init_time_step(time_step)
    self.step_time = []
    t0             = time()
    t              = t_start
    dt             = time_step
    alpha          = momentum.solve_params['solver']['newton_solver']
    alpha          = alpha['relaxation_parameter']
   
    # Loop over all times
    while t <= t_end:

      # start the timer :
      tic = time()
      
      # solve momentum equation, lower alpha on failure :
      if adaptive:
        solved_u = False
        par    = momentum.solve_params['solver']['newton_solver']
        while not solved_u:
          if par['relaxation_parameter'] < 0.2:
            status_u = [False, False]
            break
          # always reset velocity for good convergence :
          self.assign_variable(momentum.get_U(), DOLFIN_EPS)
          status_u = momentum.solve(annotate=annotate)
          solved_u = status_u[1]
          if not solved_u:
            par['relaxation_parameter'] /= 1.43
            print_text(stars, 'red', 1)
            s = ">>> WARNING: newton relaxation parameter lowered to %g <<<"
            print_text(s % par['relaxation_parameter'], 'red', 1)
            print_text(stars, 'red', 1)

      # solve velocity :
      else:
        momentum.solve(annotate=annotate)
    
      # solve mass equations, lowering time step on failure :
      if adaptive:
        solved_h = False
        while not solved_h:
          if dt < DOLFIN_EPS:
            status_h = [False,False]
            break
          H        = self.H.copy(True)
          status_h = mass.solve(annotate=annotate)
          solved_h = status_h[1]
          if t <= 100:
            solved_h = True
          if not solved_h:
            dt /= 2.0
            print_text(stars, 'red', 1)
            s = ">>> WARNING: time step lowered to %g <<<"
            print_text(s % dt, 'red', 1)
            self.init_time_step(dt)
            self.init_H_H0(H)
            print_text(stars, 'red', 1)

      # solve mass :
      else:
        mass.solve(annotate=annotate)
      
      ## use adaptive solver if desired :
      #if adaptive and (not mom_s[1] or not mas_s[1]):
      #  s = "::: reducing time step for convergence :::"
      #  print_text(s, self.color())
      #  solved, dt, t = self.adaptive_update(momentum, energy, mass,
      #                                       t_start, t_end, t,
      #                                       annotate=annotate)
      #  time_step = dt
      #  self.init_time_step(dt)
      
      # solve energy :
      energy.solve(annotate=annotate)

      # update pressure-melting point :
      energy.calc_T_melt(annotate=annotate)

      if callback != None:
        s    = '::: calling callback function :::'
        print_text(s,cls=self.this)
        callback()
       
      # increment time step :
      s = '>>> Time: %g yr, CPU time for last dt: %.3f s <<<'
      print_text(s % (t+dt, time()-tic), 'red', 1)

      t += dt
      self.step_time.append(time() - tic)
      
      # for the subsequent iteration, reset the parameters to normal :
      if adaptive:
        if par['relaxation_parameter'] != alpha:
          print_text("::: resetting alpha to normal :::", cls=self.this)
          par['relaxation_parameter'] = alpha
        if dt != time_step:
          print_text("::: resetting dt to normal :::", cls=self.this)
          self.init_time_step(time_step)
          dt = time_step
      

    # calculate total time to compute
    s = time() - t0
    m = s / 60.0
    h = m / 60.0
    s = s % 60
    m = m % 60
    text = "total time to perform transient run: %02d:%02d:%02d" % (h,m,s)
    print_text(text, 'red', 1)



