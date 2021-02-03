<%def name="kernel_signature(name)">
__global__ void ${name}(
    ${caller.body()}
    )
</%def>

<%def name="thread_guard(limit)">
    if (threadIdx.x < ${limit})
    {
        ${caller.body()}
    }
</%def>

<%def name="compile_time_parameters()">
% for par in model.parameter_names:
${decl_const_float(par, getattr(model, par)[0])}
% endfor
${decl_const_float('pi', np.pi)}
</%def>

<%def name="get2d(src,n,i,j)">${src}[${i}*${n} + ${j}]</%def>
<%def name="decl_float(name,val)">float ${name} = ${val}f;</%def>
<%def name="decl_const_float(name,val)">const ${decl_float(name,val)}</%def>

<%def name="time_loop(var='t',start=0,stop='nt')">
	for (unsigned int ${var}=${start}; ${var}<${stop}; ${var}++)
	{
		${caller.body()}
	}
</%def>

<%def name="loop_unpack_states(precision='float', states_name='state')">
	% for svar in model.state_variables:
	${precision} ${svar} = ${get2d(states_name, 'n_node', loop.index, 'id')};
	% endfor
</%def>

<%def name="loop_compute_coupling_terms()">
    % for cterm in model.coupling_terms:
    double ${cterm} = 0.0f;
    % endfor

    for (unsigned int j=0; j < n_node; j++)
    {
        float wij = ${get2d('weights', 'n_node', 'j', 'id')};
        if (wij == 0.0f)
            continue;
        % for cterm in model.coupling_terms:
        ${cterm} += wij * ${get2d('state', 'n_node', loop.index, 'j')};
        % endfor
    }

    % for cterm in model.coupling_terms:
    ${cterm} *= ${cfun_a};
    % endfor
</%def>

## TODO allow different output array
<%def name="loop_compute_derivatives(out)">
    % for svar in model.state_variables:
    ${out}[${loop.index}*n_node + id] = ${model.state_variable_dfuns[svar]};
    % endfor
</%def>

<%def name="loop_euler_update()">
	% for svar in model.state_variables:
	state[${loop.index}*n_node + id] += dt * dX[${loop.index}*n_node + id];
	% endfor
</%def>

<%def name="loop_update_trace()">
    % for svar in model.state_variables:
    trace[t*2*n_node + ${loop.index}*n_node + id] = state[${loop.index}*n_node + id];
    % endfor
</%def>