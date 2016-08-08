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
      JupyterReact.init( Jupyter, events, 'timbr.machine', { components } );
  });
}

module.exports = {
  load_ipython_extension: load_ipython_extension
};
