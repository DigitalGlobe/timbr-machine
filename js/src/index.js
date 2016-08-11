if (window.require) {
    window.require.config({
        map: {
            "*" : {
                "components": "/nbextensions/timbr_machine/components.js"
            }
        }
    });
}

import JupyterReact from 'jupyter-react-js';

function load_ipython_extension () {
  requirejs([
      "base/js/namespace",
      "base/js/events",
      "components"
  ], function( Jupyter, events, components ) {
      require('./css/timbr_machine.less');
      // initialize jupyter react cells, comm mananger and components
      
      const on_update = ( module, props, commId ) => {
        console.log('sending dispatch', commId )
        components.dispatcher.dispatch({
          actionType: module.toLowerCase() + '_update',
          data: props,
          commId
        });
      }
      JupyterReact.init( Jupyter, events, 'timbr.machine', { components, on_update } );
  });
}

module.exports = {
  load_ipython_extension: load_ipython_extension
};
